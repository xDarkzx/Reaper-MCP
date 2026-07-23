"""Drum-pattern and chord-progression helpers.

Two high-affordance tools the AI can reach for without parsing shorthand:

- `create_drum_pattern` — multi-lane step-sequencer notation (16-step default).
- `create_chord_progression` — chord names (Cm7, F#maj9, Bb7sus4) → voiced MIDI.

Both auto-create a MIDI item if `item_index=-1`, or reuse an existing one.
Call `transport_set_bpm` first if your project's tempo isn't set — the item
length in seconds depends on it.
"""

import json
import re

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


# General-MIDI drum map — the characters most drum machines agree on.
_DRUM_CHAR_TO_PITCH = {
    "k": 36,   # Kick (C1)
    "s": 38,   # Snare (D1)
    "b": 37,   # Side stick / rimshot
    "p": 39,   # Hand clap
    "h": 42,   # Hi-hat closed (F#1)
    "o": 46,   # Hi-hat open (A#1)
    "c": 49,   # Crash cymbal (C#2)
    "r": 51,   # Ride cymbal (D#2)
    "t": 47,   # Mid tom (B1)
    "l": 41,   # Low tom / floor (F1)
    "i": 45,   # High tom (A1)
    "m": 38,   # alias for snare (legacy)
}

# Chord-type suffix → semitone intervals from the root.
_CHORD_INTERVALS = {
    "":      [0, 4, 7],
    "maj":   [0, 4, 7],
    "M":     [0, 4, 7],
    "m":     [0, 3, 7],
    "min":   [0, 3, 7],
    "-":     [0, 3, 7],
    "dim":   [0, 3, 6],
    "dim7":  [0, 3, 6, 9],
    "aug":   [0, 4, 8],
    "+":     [0, 4, 8],
    "sus2":  [0, 2, 7],
    "sus4":  [0, 5, 7],
    "sus":   [0, 5, 7],
    "6":     [0, 4, 7, 9],
    "m6":    [0, 3, 7, 9],
    "7":     [0, 4, 7, 10],
    "m7":    [0, 3, 7, 10],
    "maj7":  [0, 4, 7, 11],
    "M7":    [0, 4, 7, 11],
    "7sus4": [0, 5, 7, 10],
    "add9":  [0, 4, 7, 14],
    "madd9": [0, 3, 7, 14],
    "9":     [0, 4, 7, 10, 14],
    "m9":    [0, 3, 7, 10, 14],
    "maj9":  [0, 4, 7, 11, 14],
    "M9":    [0, 4, 7, 11, 14],
    "11":    [0, 4, 7, 10, 14, 17],
    "m11":   [0, 3, 7, 10, 14, 17],
    "13":    [0, 4, 7, 10, 14, 21],
    "m13":   [0, 3, 7, 10, 14, 21],
}

_NOTE_OFFSETS = {
    "C": 0, "C#": 1, "Db": 1,
    "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "Fb": 4, "E#": 5,
    "F": 5, "F#": 6, "Gb": 6,
    "G": 7, "G#": 8, "Ab": 8,
    "A": 9, "A#": 10, "Bb": 10,
    "B": 11, "Cb": 11, "B#": 0,
}

_CHORD_RE = re.compile(r"^\s*([A-Ga-g][#b]?)(.*?)\s*$")


def _tile_pattern_lines(raw_lines: list[str], steps_per_bar: int, bar_count: int) -> list[str]:
    """Expand each drum-pattern lane to steps_per_bar * bar_count characters.

    A line exactly steps_per_bar long is repeated across all bar_count bars
    (the common case: "play this 1-bar pattern for N bars"). Any other
    length that doesn't already match the full expected length is an error
    — silently only filling the first bar and leaving the rest empty is the
    bug this guards against.
    """
    total_steps = steps_per_bar * bar_count
    tiled = []
    for raw in raw_lines:
        line = raw.strip()
        if len(line) == steps_per_bar and bar_count > 1:
            line = line * bar_count
        elif len(line) != total_steps:
            raise ValueError(
                f"Lane {line!r} has {len(line)} chars but steps_per_bar="
                f"{steps_per_bar} x bar_count={bar_count} = {total_steps} "
                f"expected (or exactly {steps_per_bar} to auto-repeat "
                "across all bars). A short line does NOT repeat on its "
                "own — pad with '.' or match one of those two lengths."
            )
        tiled.append(line)
    return tiled


def _parse_chord(name: str, base_octave: int) -> list[int] | None:
    """Return MIDI pitches for a chord like 'Cm7' or 'F#maj9'.

    Accepts either case for the root (C or c both map to C). Unknown chord
    qualities fall back to major triad. Unknown roots return None.
    """
    m = _CHORD_RE.match(name)
    if not m:
        return None
    root_raw, quality = m.group(1), m.group(2).strip()
    # Normalise: root letter uppercase, accidental kept as-is (# / b).
    root = root_raw[0].upper() + root_raw[1:]
    if root not in _NOTE_OFFSETS:
        return None
    intervals = _CHORD_INTERVALS.get(quality)
    if intervals is None:
        # Unknown quality — major fallback, but flag it upstream.
        intervals = [0, 4, 7]
    # MIDI octave convention: C4 = 60. pitch = (octave + 1) * 12 + offset.
    root_midi = (base_octave + 1) * 12 + _NOTE_OFFSETS[root]
    return [root_midi + i for i in intervals]


def _split_chord_list(chords: str) -> list[str]:
    """Accept comma, pipe, dash-with-spaces, or whitespace separators."""
    # Normalise ' - ' to comma, then split on comma / pipe / newline.
    cleaned = re.sub(r"\s*[-|]\s*", ",", chords)
    parts = re.split(r"[,\n]", cleaned)
    return [p.strip() for p in parts if p.strip()]


async def _bpm(client) -> float:
    info = await client.execute("project_get_info")
    try:
        return float(info.get("bpm", 120.0))
    except (TypeError, ValueError):
        return 120.0


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def create_drum_pattern(
        track_index: int,
        pattern: str,
        item_index: int = -1,
        start_qn: float = 0.0,
        steps_per_bar: int = 16,
        bar_count: int = 1,
        velocity: int = 100,
        channel: int = 9,
    ) -> dict:
        """Create a drum pattern from step-sequencer shorthand.

        Each line of `pattern` is one drum lane. Characters map to GM drums:
        `k`=kick, `s`=snare, `h`=hi-hat closed, `o`=hi-hat open, `c`=crash,
        `r`=ride, `t`=mid tom, `l`=low tom, `i`=high tom, `p`=clap, `b`=rimshot.
        `.` or space = rest. Any unknown character is ignored.

        Example — standard 16-step rock beat:

            k...k...k...k...
            ....s.......s...
            h.h.h.h.h.h.h.h.

        Defaults: 16 steps per bar = 1/16-note grid. `channel=9` = GM drum channel.
        Pass `item_index=-1` to auto-create a new MIDI item positioned in the
        project at `start_qn` (e.g. bar 5 in 4/4 = start_qn=16.0). Building a
        multi-section arrangement on one track? Call this once per section
        with `item_index=-1` each time and increasing `start_qn` — each call
        creates its own non-overlapping item at the right place, it does NOT
        append to a previous item.

        Returns the item index and number of notes inserted.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if not 1 <= steps_per_bar <= 64:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "steps_per_bar must be 1-64")
        if not 1 <= bar_count <= 64:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "bar_count must be 1-64")
        if not 1 <= velocity <= 127:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "velocity must be 1-127")
        if not 0 <= channel <= 15:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "channel must be 0-15")

        qn_per_step = 4.0 / steps_per_bar  # 16 steps → 0.25 QN per step
        gate = qn_per_step * 0.9            # notes end just under the next step
        bpm = await _bpm(client)
        qn_to_sec = 60.0 / bpm  # midi_insert_notes_batch expects seconds, not QN

        notes = []
        lanes_with_content = 0
        unknown_chars: set[str] = set()
        raw_lines = [ln for ln in pattern.splitlines() if ln.strip()]
        if not raw_lines:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "pattern is empty")

        total_steps = steps_per_bar * bar_count
        try:
            tiled_lines = _tile_pattern_lines(raw_lines, steps_per_bar, bar_count)
        except ValueError as e:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, str(e))

        for line in tiled_lines:
            had_hit = False
            step_in_lane = 0
            for ch in line:
                if step_in_lane >= total_steps:
                    break
                if ch == "." or ch == " ":
                    step_in_lane += 1
                    continue
                pitch = _DRUM_CHAR_TO_PITCH.get(ch.lower())
                if pitch is None:
                    unknown_chars.add(ch)
                    step_in_lane += 1
                    continue
                # start_qn is the pattern's absolute position in QN (project
                # time when auto-creating; must match the pre-created item's
                # position if item_index was passed explicitly — see
                # midi_insert_notes_batch, which uses absolute project time).
                start = start_qn + step_in_lane * qn_per_step
                notes.append({
                    "pitch": pitch,
                    "velocity": velocity,
                    "start": start * qn_to_sec,
                    "end": (start + gate) * qn_to_sec,
                    "channel": channel,
                })
                had_hit = True
                step_in_lane += 1
            if had_hit:
                lanes_with_content += 1

        if not notes:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"No drum hits parsed. Unknown chars: {sorted(unknown_chars)}. "
                f"Use k/s/h/o/c/r/t/l/i/p/b for drum hits, '.' for rests.",
            )

        created_item = False
        if item_index < 0:
            total_qn = steps_per_bar * qn_per_step * bar_count
            # No pad — any positive pad, even a tiny epsilon, guarantees
            # overlap with a next section's item placed back-to-back at
            # this section's end (confirmed: 0.5s pad overlapped by 0.5s,
            # 0.05s pad by 0.05s, 0.001s pad by 0.001s — it's proportional,
            # not a rounding artifact). Each drum note already ends 10% of a
            # step early (see `gate` above), so the last note's tail is
            # already inside total_qn with headroom to spare.
            length_sec = total_qn * qn_to_sec
            # Item is positioned in the project at start_qn — notes use
            # absolute project time (see midi_insert_notes_batch), so the
            # item boundary must start where the pattern actually starts.
            # Otherwise a second call for a later section (different
            # start_qn) would create an item that overlaps this one, since
            # both would sit at project position 0.
            position_sec = start_qn * qn_to_sec
            result = await client.execute(
                "item_create_midi",
                track_index=track_index,
                position=position_sec,
                length=length_sec,
            )
            data = result.get("data", result)
            item_index = int(data.get("item_index", data.get("index", 0)))
            created_item = True

        await client.execute(
            "midi_insert_notes_batch",
            track_index=track_index,
            item_index=item_index,
            notes=json.dumps(notes),
        )

        hint = f"Inserted {len(notes)} drum hits across {lanes_with_content} lane(s)."
        if unknown_chars:
            hint += f" Ignored unknown chars: {sorted(unknown_chars)}."
        hint += " Call midi_humanize() for timing/velocity variation."

        return {
            "item_index": item_index,
            "notes_inserted": len(notes),
            "lanes": lanes_with_content,
            "item_created": created_item,
            "steps_per_bar": steps_per_bar,
            "bar_count": bar_count,
            "unknown_chars": sorted(unknown_chars),
            "hint": hint,
        }

    @mcp.tool()
    async def create_chord_progression(
        track_index: int,
        chords: str,
        item_index: int = -1,
        start_qn: float = 0.0,
        chord_duration_qn: float = 4.0,
        velocity: int = 96,
        channel: int = 0,
        base_octave: int = 4,
    ) -> dict:
        """Insert a chord progression as voiced MIDI notes.

        Accepts chords separated by commas, pipes, dashes, or newlines:
        `"Cm7, Fm7, Bb7, Eb"` or `"Am - F - C - G"` or `"Dm | G | Em | A"`.

        Supported qualities: maj, m/min, dim, dim7, aug, sus2, sus4,
        6, m6, 7, m7, maj7, add9, 9, m9, maj9, 11, m11, 13, m13.

        `base_octave=4` places C as MIDI 60 (middle C). Each chord occupies
        `chord_duration_qn` quarter notes (default 4 QN = one bar at 4/4).

        Pass `item_index=-1` to auto-create a MIDI item positioned in the
        project at `start_qn` (e.g. bar 5 in 4/4 = start_qn=16.0). Building a
        multi-section arrangement on one track? Call this once per section
        with `item_index=-1` each time and increasing `start_qn` — each call
        creates its own non-overlapping item at the right place, it does NOT
        append to a previous item.

        Returns the item index, number of chords placed, and any that failed to parse.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if chord_duration_qn <= 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "chord_duration_qn must be > 0")
        if not 1 <= velocity <= 127:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "velocity must be 1-127")
        if not 0 <= channel <= 15:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "channel must be 0-15")
        if not -2 <= base_octave <= 8:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "base_octave must be -2..8")

        chord_names = _split_chord_list(chords)
        if not chord_names:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "chords is empty")

        bpm = await _bpm(client)
        qn_to_sec = 60.0 / bpm  # midi_insert_notes_batch expects seconds, not QN

        notes = []
        cursor = start_qn
        parsed: list[dict] = []
        failed: list[str] = []
        for name in chord_names:
            pitches = _parse_chord(name, base_octave)
            if pitches is None:
                failed.append(name)
                cursor += chord_duration_qn
                continue
            for p in pitches:
                if not 0 <= p <= 127:
                    continue
                notes.append({
                    "pitch": p,
                    "velocity": velocity,
                    "start": cursor * qn_to_sec,
                    "end": (cursor + chord_duration_qn) * qn_to_sec,
                    "channel": channel,
                })
            parsed.append({"name": name, "pitches": pitches, "start_qn": cursor})
            cursor += chord_duration_qn

        if not notes:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"No chords parsed. Failed: {failed}",
            )

        created_item = False
        if item_index < 0:
            total_qn = chord_duration_qn * len(chord_names)
            # No pad — see create_drum_pattern's comment (any positive pad,
            # even a tiny epsilon, guarantees overlap with a next section's
            # item placed back-to-back at this one's end). The last chord's
            # note-end and this item's end are computed from the same
            # total_qn * qn_to_sec term, so they land together.
            length_sec = total_qn * qn_to_sec
            # Item is positioned in the project at start_qn — see the matching
            # comment in create_drum_pattern for why (notes use absolute
            # project time, so the item boundary must match or a later
            # section's item would overlap this one at position 0).
            position_sec = start_qn * qn_to_sec
            result = await client.execute(
                "item_create_midi",
                track_index=track_index,
                position=position_sec,
                length=length_sec,
            )
            data = result.get("data", result)
            item_index = int(data.get("item_index", data.get("index", 0)))
            created_item = True

        await client.execute(
            "midi_insert_notes_batch",
            track_index=track_index,
            item_index=item_index,
            notes=json.dumps(notes),
        )

        hint = f"Inserted {len(parsed)} chord(s), {len(notes)} notes total."
        if failed:
            hint += f" Failed to parse: {failed}."
        hint += " For rhythmic strumming / arpeggios, use midi_insert_notes_batch with per-note timing."

        return {
            "item_index": item_index,
            "item_created": created_item,
            "chords_placed": parsed,
            "notes_inserted": len(notes),
            "failed_chords": failed,
            "hint": hint,
        }
