"""Vocal-chop primitives + helpers.

Building blocks for slicing, pitching, time-stretching, reversing, and
duplicating audio items in REAPER. Style-agnostic — works for vocals,
drums, FX, anything. Designed for the workflow:

    1. User loads an audio item on a track in REAPER (vocal acapella, etc.)
    2. AI calls `track_get_all` + `item_get_all` to find it.
    3. AI uses these tools to slice, repitch, sequence, layer the audio
       into a musical chop arrangement.

The artistic decisions (which slice, what pitch, what rhythm) live in the
AI. These tools do the mechanical work without imposing taste.

Phase 1 — Primitives:
    item_split_at_transients, item_split_at_positions, take_set_pitch,
    take_set_playrate, take_set_reversed, item_duplicate.

Phase 2 — Higher-level helpers:
    analyze_chop_set, arrange_chops_to_chord_tones, stack_chop_layers.

All tools operate on item indices the AI already has — no file loading.
"""

import json
import random
import re

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


# ─────────────────── Chop pipeline style library ─────────────────────
# Per-style config is density + layering — NOT a sparse slot mask.
# Every slot is filled contiguously (chop length = slot length) so the
# listener never hears gaps of silence between chops. Styles differ by:
#   - grid_per_bar: 1/16 (dense, modern EDM), 1/8 (chillstep phrases),
#                   1/32 (stutter-heavy / Mura Masa).
#   - stutter_slots: slots to replace with rapid sub-chops (same slot time).
#   - bar_reorder:  "permuted" = each bar reshuffles source-slice order
#                    for variation; "sequential" = natural phrase flow.
#   - layer_intervals: extra harmony tracks built as SEPARATE child tracks
#                      (octave + fifth), not same-track overlays.
#
# Uniform pitch transpose (source_key → target_key) is applied per-pipeline,
# not per-slot. Per-slot retuning is explicitly rejected by the design.
_STYLE_CONFIGS = {
    "future_bass": {
        "grid_per_bar": 16,
        "stutter_slots_per_bar": [12, 15],
        "bar_reorder": "permuted",
        "layer_intervals": [12, 7],           # octave + fifth stacks
        "layer_volumes_db": [-9, -12],
    },
    "chillstep": {
        "grid_per_bar": 8,                    # longer chops, phrase feel
        "stutter_slots_per_bar": [],
        "bar_reorder": "sequential",
        "layer_intervals": [],
        "layer_volumes_db": [],
    },
    "porter": {
        "grid_per_bar": 16,
        "stutter_slots_per_bar": [4, 8, 12],
        "bar_reorder": "permuted",
        "layer_intervals": [12],              # octave only
        "layer_volumes_db": [-9],
    },
    "trap": {
        "grid_per_bar": 16,
        "stutter_slots_per_bar": [14],
        "bar_reorder": "permuted",
        "layer_intervals": [],
        "layer_volumes_db": [],
    },
    "mura_masa": {
        "grid_per_bar": 32,                   # 1/32 — tight stutter density
        "stutter_slots_per_bar": [],
        "bar_reorder": "permuted",
        "layer_intervals": [12],
        "layer_volumes_db": [-12],
    },
    "odesza": {
        "grid_per_bar": 8,
        "stutter_slots_per_bar": [],
        "bar_reorder": "sequential",
        "layer_intervals": [],
        "layer_volumes_db": [],
    },
}


# --- Chord parsing (mirrors patterns_tools._parse_chord; duplicated here
#     to keep the module self-contained). Returns (root_semitone, intervals).
_NOTE_OFFSETS = {
    "C": 0, "C#": 1, "Db": 1,
    "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "Fb": 4, "E#": 5,
    "F": 5, "F#": 6, "Gb": 6,
    "G": 7, "G#": 8, "Ab": 8,
    "A": 9, "A#": 10, "Bb": 10,
    "B": 11, "Cb": 11, "B#": 0,
}
_CHORD_INTERVALS = {
    "":      [0, 4, 7],          "maj":   [0, 4, 7],         "M":     [0, 4, 7],
    "m":     [0, 3, 7],          "min":   [0, 3, 7],         "-":     [0, 3, 7],
    "dim":   [0, 3, 6],          "dim7":  [0, 3, 6, 9],
    "aug":   [0, 4, 8],          "+":     [0, 4, 8],
    "sus2":  [0, 2, 7],          "sus4":  [0, 5, 7],         "sus":   [0, 5, 7],
    "6":     [0, 4, 7, 9],       "m6":    [0, 3, 7, 9],
    "7":     [0, 4, 7, 10],      "m7":    [0, 3, 7, 10],
    "maj7":  [0, 4, 7, 11],      "M7":    [0, 4, 7, 11],
    "9":     [0, 4, 7, 10, 14],  "m9":    [0, 3, 7, 10, 14],
    "maj9":  [0, 4, 7, 11, 14],  "add9":  [0, 4, 7, 14],
}
_CHORD_RE = re.compile(r"^\s*([A-Ga-g][#b]?)(.*?)\s*$")


def _parse_chord(name: str) -> tuple[int, list[int]] | None:
    """Return (root_semitone, intervals) for a chord like `Cm7`. None if unknown."""
    m = _CHORD_RE.match(name)
    if not m:
        return None
    root_raw = m.group(1)
    root = root_raw[0].upper() + root_raw[1:]
    if root not in _NOTE_OFFSETS:
        return None
    quality = m.group(2).strip()
    intervals = _CHORD_INTERVALS.get(quality, [0, 4, 7])
    return _NOTE_OFFSETS[root], intervals


def _split_chord_list(chords: str) -> list[str]:
    cleaned = re.sub(r"\s*[-|]\s*", ",", chords)
    parts = re.split(r"[,\n]", cleaned)
    return [p.strip() for p in parts if p.strip()]


_KEY_RE = re.compile(r"^\s*([A-Ga-g][#b]?)\s*(m|min|minor|maj|major|Maj)?\s*$")


def _parse_key(s: str) -> int | None:
    """Parse a key name like `Am`, `A minor`, `C#`, `Ebm` → root semitone (0-11).

    Mode ("m" / "maj") is accepted but ignored — we only need the root for
    uniform transpose math. Returns None if unparseable.
    """
    m = _KEY_RE.match(s or "")
    if not m:
        return None
    root_raw = m.group(1)
    root = root_raw[0].upper() + (root_raw[1:] if len(root_raw) > 1 else "")
    return _NOTE_OFFSETS.get(root)


def _shortest_shift(source_semi: int, target_semi: int) -> int:
    """Shortest signed semitone shift from source to target (range -5..+6).

    Keeps transpose within tritone bounds so formant-preserved pitch shift
    stays acceptable. Caller is responsible for deciding whether to apply
    further clamping (e.g. ±5 with formant, ±2 without).
    """
    diff = (target_semi - source_semi) % 12
    if diff > 6:
        diff -= 12
    return diff


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def item_split_at_transients(item_index: int) -> dict:
        """Slice an audio item at every detected transient.

        Uses REAPER's native transient detection (action 40310). Sensitivity
        is controlled by REAPER's project settings (Options → Preferences →
        Project → Item handling → Transient detection sensitivity), not
        by this tool — set it once in REAPER and it applies to every call.

        Args:
            item_index: Global 0-based item index of the source audio item.

        Returns:
            chops_created: number of new items created from the split.
            chops_total: total items now spanning the original time range.
            chops: list of `{item_index, position, length, offset_in_original_sec}`
                   in playback order. The AI uses these indices to repitch /
                   duplicate / reverse individual chops.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        return await client.execute("item_split_at_transients", item_index=item_index)

    @mcp.tool()
    async def item_split_at_positions(item_index: int, positions: str) -> dict:
        """Slice an item at a list of absolute project-time positions.

        For grid-based or hand-picked chopping where transient detection
        isn't right. Pass positions in seconds; positions outside the
        item's range are silently ignored.

        Args:
            item_index: Global 0-based item index.
            positions: JSON array of absolute project-time positions
                       (seconds). Example: `"[1.5, 2.0, 2.5, 3.0]"`.

        Returns the resulting chops in playback order with their indices,
        positions, lengths, and offset relative to the original item start.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        try:
            parsed = json.loads(positions)
        except json.JSONDecodeError as e:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"positions must be a JSON array: {e.msg}",
            )
        if not isinstance(parsed, list):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "positions must be a JSON array")
        if len(parsed) == 0:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "positions array is empty")
        if len(parsed) > 500:
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE,
                f"too many positions ({len(parsed)}) — max 500 per call",
            )
        for i, v in enumerate(parsed):
            if not isinstance(v, (int, float)):
                raise ReaperMCPError(
                    ErrorCode.INVALID_PARAMETER,
                    f"positions[{i}] must be numeric, got {type(v).__name__}",
                )
        return await client.execute(
            "item_split_at_positions", item_index=item_index, positions=positions,
        )

    @mcp.tool()
    async def take_set_pitch(
        item_index: int,
        semitones: float,
        take_index: int = -1,
    ) -> dict:
        """Pitch-shift a take by N semitones (no time change).

        The core of "tune a chop to a chord tone". Pass positive values to
        shift up, negative for down. Range is roughly -60 to +60 (REAPER
        clamps extremes). Half-semitone values work (`0.5`, `-1.25`, etc.)
        for fine-tuning.

        Pitch quality depends on REAPER's per-take pitch shift mode setting
        (Item Properties → Take pitch shift mode). For vocals, "Élastique
        Pro Soloist" preserves formants well. Set it once in REAPER's
        project defaults and it applies to every chop.

        Args:
            item_index: Global 0-based item index.
            semitones: Pitch shift in semitones. Float. Default 0 (no change).
            take_index: 0-based take index, or -1 for the active take.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if not -60 <= semitones <= 60:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "semitones must be in [-60, 60]")
        return await client.execute(
            "take_set_pitch",
            item_index=item_index, semitones=semitones, take_index=take_index,
        )

    @mcp.tool()
    async def take_set_playrate(
        item_index: int,
        rate: float,
        preserve_pitch: bool = True,
    ) -> dict:
        """Time-stretch a take by changing its playrate.

        With `preserve_pitch=True` (default), audio plays slower/faster
        without changing pitch — useful for fitting a chop to a beat grid.
        With `preserve_pitch=False`, this becomes a vinyl-style speed change
        (faster = higher pitch).

        After changing the rate, the item's visible length in the timeline
        does NOT auto-resize. Call `item_set_length` afterwards to match.

        Args:
            item_index: Global 0-based item index.
            rate: Playback rate. 1.0 = normal, 0.5 = half speed, 2.0 = double.
                  Range 0.05 to 16.0.
            preserve_pitch: Time-stretch without pitch change. Default True.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if not 0.05 <= rate <= 16.0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "rate must be in [0.05, 16.0]")
        return await client.execute(
            "take_set_playrate",
            item_index=item_index, rate=rate, preserve_pitch=preserve_pitch,
        )

    @mcp.tool()
    async def take_set_reversed(item_index: int) -> dict:
        """Reverse an item's audio.

        Uses REAPER's "Item: Reverse items as new take" action — the new
        reversed take becomes the active one, the original take is kept
        (item now has 2 takes). To revert, switch back to the original
        take via `item_take_set_active`.

        Useful for: reverse-cymbal-into-downbeat fills, breath-in vocal FX,
        glitchy chop reversals (Skrillex / Flume style).

        Args:
            item_index: Global 0-based item index.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        return await client.execute("take_set_reversed", item_index=item_index)

    @mcp.tool()
    async def item_duplicate(
        item_index: int,
        count: int,
        spacing_sec: float = 0.0,
    ) -> dict:
        """Copy an item N times at fixed spacing.

        Each copy is a full clone — same source, same take properties
        (pitch, playrate, FX, fades). Used for the Porter Robinson
        1/16 stutter, EDM build-up risers, percussive vocal repeats.

        With default spacing (0), copies are placed back-to-back at the
        original item's length. For tight stutters, pass a small spacing
        like `60/bpm/4` for 1/16-note repeats at the project's tempo.

        Args:
            item_index: Global 0-based source item index.
            count: Number of copies to make. Range 1-100.
            spacing_sec: Time between copy starts in seconds. 0 = use
                         item length (back-to-back). Default 0.

        Returns the new clones with their `item_index` so the AI can
        manipulate them (pitch, fade, etc.) directly.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if not 1 <= count <= 100:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "count must be 1-100")
        if spacing_sec < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "spacing_sec must be >= 0")
        return await client.execute(
            "item_duplicate",
            item_index=item_index, count=count, spacing_sec=spacing_sec,
        )

    # ─────────────────── Phase 2 — high-level helpers ─────────────────────

    @mcp.tool()
    async def analyze_chop_set(item_indices: str) -> dict:
        """Inspect a list of chops and classify each by duration.

        Pure-Python helper that calls `item_get_info` for each index and
        returns enriched per-chop info plus summary stats. Helps the AI
        pick which chops to use for which musical role without doing
        audio content analysis.

        Duration classes:
            hit       — < 150 ms (drum hit, consonant burst)
            staccato  — 150-400 ms (short syllable, good for stutters)
            syllable  — 400 ms-1 s (full syllable / word)
            sustain   — > 1 s (phrase / vowel held)

        Args:
            item_indices: JSON array of item indices. Up to 200 chops.
        """
        try:
            indices = json.loads(item_indices)
        except json.JSONDecodeError as e:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"item_indices must be a JSON array: {e.msg}",
            )
        if not isinstance(indices, list):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "item_indices must be a JSON array")
        if not 1 <= len(indices) <= 200:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_indices length must be 1-200")
        for i, v in enumerate(indices):
            if not isinstance(v, int) or v < 0:
                raise ReaperMCPError(
                    ErrorCode.INVALID_PARAMETER,
                    f"item_indices[{i}] must be a non-negative integer",
                )

        chops_info = []
        errors = []
        for idx in indices:
            try:
                info = await client.execute("item_get_info", item_index=idx)
                data = info.get("data", info)
                length = float(data.get("length", 0))
                position = float(data.get("position", 0))
                if length < 0.15:
                    cls = "hit"
                elif length < 0.4:
                    cls = "staccato"
                elif length < 1.0:
                    cls = "syllable"
                else:
                    cls = "sustain"
                chops_info.append({
                    "item_index": idx,
                    "position_sec": round(position, 4),
                    "length_sec": round(length, 4),
                    "duration_class": cls,
                })
            except Exception as e:
                errors.append({"item_index": idx, "error": str(e)})

        # Summary stats
        by_class: dict[str, int] = {}
        total_dur = 0.0
        for c in chops_info:
            by_class[c["duration_class"]] = by_class.get(c["duration_class"], 0) + 1
            total_dur += c["length_sec"]
        avg_dur = (total_dur / len(chops_info)) if chops_info else 0.0

        # Sort chops by position so the AI gets them in playback order
        chops_info.sort(key=lambda c: c["position_sec"])

        return {
            "total_chops": len(chops_info),
            "by_class": by_class,
            "average_duration_sec": round(avg_dur, 4),
            "total_span_sec": round(
                (chops_info[-1]["position_sec"] + chops_info[-1]["length_sec"] -
                 chops_info[0]["position_sec"]) if chops_info else 0.0, 4
            ),
            "chops": chops_info,
            "errors": errors,
            "hint": (
                f"{len(chops_info)} chops, "
                f"{by_class.get('hit', 0)} hit / {by_class.get('staccato', 0)} staccato / "
                f"{by_class.get('syllable', 0)} syllable / {by_class.get('sustain', 0)} sustain. "
                f"Use staccato chops for Porter-style stutters, syllables for chord-tone "
                f"melodies, sustains for atmospheric layers."
            ),
        }

    @mcp.tool()
    async def arrange_chops_to_chord_tones(
        item_indices: str,
        chord_progression: str,
        beats_per_chord: int = 4,
        bpm: float = 0.0,
        layout: str = "follow",
        source_root: str = "C",
    ) -> dict:
        """[NICHE] Retune each chop to a chord tone.

        ⚠️  WARNING: This is NOT how professional vocal chops are made.
        Per-slice chord-tone retuning smears vocal formants and sounds
        unnatural. `chop_pipeline` uses uniform transpose instead, which
        is the correct default for EDM vocal chops.

        This tool is kept for stylized experimental use (e.g., glitch /
        granular / heavily-processed chop effects where the pitched-up-
        demon-voice sound is the desired character). DO NOT use it as
        your default chop workflow.

        Walks the chops in playback order. For each chop, determines
        which chord it falls within (based on its time position) and
        picks a chord tone according to `layout`. Applies the pitch
        shift via `take_set_pitch`.

        Args:
            item_indices: JSON array of chop item indices (in playback order).
                          Typically the `chops` list returned by
                          `item_split_at_transients`.
            chord_progression: Chord names separated by commas, pipes,
                               or dashes-with-spaces. E.g.,
                               `"Cm7, Fm7, Bb7, Eb"` or `"Am - F - C - G"`.
            beats_per_chord: How many beats each chord lasts. Default 4
                             (one bar per chord at 4/4).
            bpm: Project tempo. Pass 0 to fetch from REAPER (extra round-trip).
            layout: How to pick a chord tone for each chop:
                - `follow`     — cycle root → 3rd → 5th → root → 3rd → 5th
                - `ascending`  — climb chord tones across each chord
                - `porter`     — root → 5th → octave → 5th → root (Porter Robinson)
                - `root`       — every chop = root of current chord
            source_root: Note name the source vocal is "in". Pitch shifts
                         are computed relative to this. Default `"C"`.
                         If you don't know, leave as `C`; the result will
                         still be musical relative to the chord changes,
                         just not in absolute key.
        """
        if layout not in ("follow", "ascending", "porter", "root"):
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                "layout must be follow / ascending / porter / root",
            )
        try:
            indices = json.loads(item_indices)
        except json.JSONDecodeError as e:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, f"item_indices: {e.msg}")
        if not isinstance(indices, list) or not indices:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "item_indices must be a non-empty JSON array")
        if not 1 <= beats_per_chord <= 16:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "beats_per_chord must be 1-16")
        if bpm < 0 or bpm > 400:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "bpm must be 0..400")

        if source_root not in _NOTE_OFFSETS:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, f"unknown source_root: {source_root}")
        source_offset = _NOTE_OFFSETS[source_root]

        # Parse chord progression
        chord_names = _split_chord_list(chord_progression)
        if not chord_names:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "chord_progression is empty")
        chords = []
        failed_chords = []
        for name in chord_names:
            parsed = _parse_chord(name)
            if parsed is None:
                failed_chords.append(name)
                chords.append((0, [0, 4, 7]))  # fallback to C major
            else:
                chords.append(parsed)

        # Get BPM if not supplied
        if bpm == 0:
            ts = await client.execute("transport_get_state")
            tdata = ts.get("data", ts)
            bpm = float(tdata.get("bpm", 120.0))

        seconds_per_beat = 60.0 / bpm
        chord_length_sec = beats_per_chord * seconds_per_beat
        progression_length_sec = chord_length_sec * len(chords)

        # Sort chops by position so we walk them in playback order
        chop_info = []
        for idx in indices:
            info = await client.execute("item_get_info", item_index=idx)
            d = info.get("data", info)
            chop_info.append({
                "item_index": idx,
                "position_sec": float(d.get("position", 0)),
            })
        chop_info.sort(key=lambda c: c["position_sec"])

        # Determine each chop's chord + pick a chord tone via the layout
        first_chop_pos = chop_info[0]["position_sec"] if chop_info else 0.0
        per_chord_count: dict[int, int] = {}  # how many chops have landed in each chord so far
        applied = []
        skipped = []

        for chop in chop_info:
            relative_sec = chop["position_sec"] - first_chop_pos
            chord_idx = int(relative_sec // chord_length_sec) if chord_length_sec > 0 else 0
            if chord_idx >= len(chords):
                # Past the end of the progression — wrap around
                chord_idx = chord_idx % len(chords)

            chord_root, chord_intervals = chords[chord_idx]
            chord_pos_in_progression = per_chord_count.get(chord_idx, 0)
            per_chord_count[chord_idx] = chord_pos_in_progression + 1

            # Pick chord tone offset by layout
            n_intervals = len(chord_intervals)
            if layout == "root":
                tone_offset = 0
            elif layout == "follow":
                # Cycle through chord tones
                tone_offset = chord_intervals[chord_pos_in_progression % n_intervals]
            elif layout == "ascending":
                # Climb tones, then octave, then re-climb
                step = chord_pos_in_progression
                octave = step // n_intervals
                tone_offset = chord_intervals[step % n_intervals] + (12 * octave)
                # Cap so we don't run away
                if tone_offset > 24:
                    tone_offset = chord_intervals[chord_pos_in_progression % n_intervals]
            elif layout == "porter":
                # root → 5th → octave → 5th → root
                porter_pattern = [0, 7, 12, 7]
                tone_offset = porter_pattern[chord_pos_in_progression % len(porter_pattern)]

            # Compute final pitch shift relative to the source's "root"
            target_pitch_semis = chord_root + tone_offset  # absolute
            shift_from_source = target_pitch_semis - source_offset
            # Pull into a reasonable range (-24 to +24)
            while shift_from_source > 24:
                shift_from_source -= 12
            while shift_from_source < -24:
                shift_from_source += 12

            try:
                await client.execute(
                    "take_set_pitch",
                    item_index=chop["item_index"],
                    semitones=float(shift_from_source),
                    take_index=-1,
                )
                applied.append({
                    "item_index": chop["item_index"],
                    "position_sec": round(chop["position_sec"], 4),
                    "chord_idx": chord_idx,
                    "chord_name": chord_names[chord_idx % len(chord_names)],
                    "tone_offset": tone_offset,
                    "pitch_semis": shift_from_source,
                })
            except Exception as e:
                skipped.append({"item_index": chop["item_index"], "error": str(e)})

        return {
            "layout": layout,
            "bpm": bpm,
            "chord_count": len(chords),
            "beats_per_chord": beats_per_chord,
            "progression_length_sec": round(progression_length_sec, 4),
            "source_root": source_root,
            "chops_pitched": len(applied),
            "applied": applied,
            "skipped": skipped,
            "failed_chords": failed_chords,
            "hint": (
                f"Pitched {len(applied)} chops over {len(chords)} chords ({layout}). "
                f"Hit play to hear it. To layer harmonies, call stack_chop_layers next."
            ),
        }

    @mcp.tool()
    async def chop_pipeline(
        vocal_item_index: int,
        chord_progression: str = "",
        bpm: float = 0.0,
        bars: int = 4,
        style: str = "future_bass",
        target_track_name: str = "Vocal Chops",
        mute_original: bool = True,
        source_key: str = "C",
        target_key: str = "",
        mode: str = "slice-preserve",
        seed: int = 0,
    ) -> dict:
        """End-to-end vocal-chop arrangement (redesigned for pro workflow).

        Produces a contiguous, key-matched, professionally-structured chop
        arrangement on a new track. Follows researched EDM vocal-chop rules:

          • CHOPS ARE CONTIGUOUS — every slot filled wall-to-wall, no
            silence gaps. Slot length is determined by the grid.
          • PITCH IS UNIFORM — the whole chop set is transposed ONCE to
            match the track key (source_key → target_key). No per-slice
            chord-tone retuning; that destroys formants and sounds bad.
          • LAYER STACKS ARE SEPARATE TRACKS — octave/fifth layers are
            duplicate child tracks at reduced volume (not overlays that
            smear the lead).
          • BAR-LEVEL VARIATION — each bar pulls a different permutation
            of source slices, so the arrangement doesn't just loop.

        REQUIREMENT for clean pitch: set REAPER's per-item pitch-shift mode
        to "élastique Pro Soloist Monophonic" (Project Settings → Media
        Item Defaults, or per-take in Item Properties). Raw pitch shift
        without formant preservation destroys vocal character. The tool
        does not auto-set this (requires REAPER user config).

        Modes:
          • `slice-preserve` (default): slice source at a 1/16 (or 1/8 /
            1/32 per style) grid, reorder slices across bars for variation,
            apply ONE uniform pitch shift to all chops.
          • `melody`: pick a central vowel offset in the source, write a
            chord-tone melody across bars (root/3rd/5th of each chord),
            capped at ±5 semitones from source. Requires
            `chord_progression`. Approximates the "one vowel + sampler +
            MIDI melody" workflow (Flume / Simpler / Quick Sampler).

        Args:
            vocal_item_index: Global 0-based index of the vocal item.
            chord_progression: Chord list (required for `melody` mode,
                               optional for `slice-preserve`). E.g.
                               `"Fm, Ab, Bb, Fm"`.
            bpm: Project tempo. 0 = fetch from REAPER.
            bars: Length in bars. Default 4, max 32.
            style: One of `future_bass`, `chillstep`, `porter`, `trap`,
                   `mura_masa`, `odesza`. Drives grid / stutter / layers.
            target_track_name: Name for the new track.
            mute_original: Mute the source vocal's track. Default True.
            source_key: Vocal's original musical key. Accepts `Am`,
                        `A minor`, `A`, `Ebm`, etc. Default `C`.
            target_key: Track key to transpose TO. Empty = use root of
                        first chord in `chord_progression`, or source_key
                        if no progression given.
            mode: `slice-preserve` (default) or `melody`. See above.
            seed: Random seed for bar permutations. 0 = nondeterministic.
        """
        # ────────── Validate inputs ──────────
        if vocal_item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "vocal_item_index must be >= 0")
        if style not in _STYLE_CONFIGS:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"style must be one of {list(_STYLE_CONFIGS.keys())}",
            )
        if mode not in ("slice-preserve", "melody"):
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                "mode must be 'slice-preserve' or 'melody'",
            )
        if not 1 <= bars <= 32:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "bars must be 1-32")
        if bpm < 0 or bpm > 400:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "bpm must be 0-400")

        source_root = _parse_key(source_key)
        if source_root is None:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, f"unknown source_key: {source_key}")

        # ────────── Resolve BPM ──────────
        if bpm == 0:
            ts = await client.execute("transport_get_state")
            tdata = ts.get("data", ts)
            bpm = float(tdata.get("bpm", 120.0))
        seconds_per_beat = 60.0 / bpm
        bar_length_sec = seconds_per_beat * 4.0

        # ────────── Parse chord progression ──────────
        chord_names = _split_chord_list(chord_progression) if chord_progression else []
        chords: list[tuple[int, list[int]]] = []
        failed_chords: list[str] = []
        for name in chord_names:
            parsed = _parse_chord(name)
            if parsed is None:
                failed_chords.append(name)
                chords.append((source_root, [0, 4, 7]))
            else:
                chords.append(parsed)

        if mode == "melody" and not chords:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                "mode='melody' requires chord_progression",
            )

        # ────────── Compute the UNIFORM pitch transpose ──────────
        # Rule: source_key → target_key, capped ±6 semis (tritone).
        # Everything after this uses this single value — no per-slot retune.
        target_root = _parse_key(target_key) if target_key else None
        if target_root is None and chords:
            target_root = chords[0][0]
        if target_root is None:
            target_root = source_root  # no progression + no target_key → don't shift
        uniform_shift = _shortest_shift(source_root, target_root)
        pitch_warning = None
        if abs(uniform_shift) >= 5:
            pitch_warning = (
                f"Uniform transpose is {uniform_shift} semitones — at the edge "
                f"of formant-preserved territory. Consider changing source vocal "
                f"or target key for a cleaner sound."
            )

        cfg = _STYLE_CONFIGS[style]
        grid_per_bar = cfg["grid_per_bar"]
        stutter_slots = set(cfg["stutter_slots_per_bar"])
        bar_reorder = cfg["bar_reorder"]
        layer_intervals = list(cfg["layer_intervals"])
        layer_volumes_db = list(cfg["layer_volumes_db"])
        seconds_per_slot = bar_length_sec / grid_per_bar

        # ────────── Read source info ──────────
        src_info_result = await client.execute(
            "item_get_source_info", item_index=vocal_item_index,
        )
        src_data = src_info_result.get("data", src_info_result)
        source_file = src_data.get("source_file", "")
        source_length = float(src_data.get("source_length_sec", 0.0))
        if not source_file or source_length <= 0:
            raise ReaperMCPError(
                ErrorCode.COMMAND_FAILED,
                f"Could not resolve source file for item {vocal_item_index}: {src_info_result}",
            )

        # Inherit the source item's playrate so derived chops stay in-tempo
        # when source BPM differs from project BPM. REAPER typically sets
        # this automatically when dropping a BPM-tagged loop into a project
        # of different tempo (e.g. 128 BPM vocal → 96 BPM project → 0.75).
        playrate = float(src_data.get("take_playrate", 1.0) or 1.0)
        if playrate <= 0:
            playrate = 1.0
        # Source-time per slot = project-time per slot * playrate.
        seconds_per_slot_source = seconds_per_slot * playrate
        num_source_slices = max(1, int(source_length / seconds_per_slot_source))

        rng = random.Random(seed) if seed else random.Random()

        # ────────── Create target track + layer tracks ──────────
        tr_result = await client.execute("track_create", name=target_track_name)
        tr_data = tr_result.get("data", tr_result)
        target_track_idx = tr_data.get("index", tr_data.get("track_index"))
        if target_track_idx is None:
            raise ReaperMCPError(ErrorCode.COMMAND_FAILED, f"Failed to create target track: {tr_result}")
        target_track_idx = int(target_track_idx)

        layer_tracks: list[dict] = []  # [{interval, track_index, volume_db}]
        for interval, vol_db in zip(layer_intervals, layer_volumes_db):
            suffix = "+oct" if interval == 12 else ("+5th" if interval == 7 else f"+{interval}st")
            layer_name = f"{target_track_name} {suffix}"
            lt_res = await client.execute("track_create", name=layer_name)
            lt_data = lt_res.get("data", lt_res)
            lt_idx = lt_data.get("index", lt_data.get("track_index"))
            if lt_idx is not None:
                lt_idx = int(lt_idx)
                try:
                    await client.execute("track_set_volume", track_index=lt_idx, volume_db=float(vol_db))
                except Exception:
                    pass
                layer_tracks.append({"interval": interval, "track_index": lt_idx, "volume_db": vol_db})

        vocal_track_idx = int(src_data.get("track_index", -1))

        # ────────── Decide pitches per slot ──────────
        # slice-preserve: every slot = uniform_shift.
        # melody: each slot pitch = uniform_shift + chord_tone_within_±5.
        def _pitch_for_slot(bar_idx: int, slot_idx: int) -> int:
            if mode == "slice-preserve" or not chords:
                return uniform_shift
            # melody: determine chord for this slot
            total_slots = bars * grid_per_bar
            slot_global = bar_idx * grid_per_bar + slot_idx
            chord_idx = int((slot_global * len(chords)) / total_slots) if total_slots else 0
            chord_idx = min(chord_idx, len(chords) - 1)
            chord_root, chord_intervals = chords[chord_idx]
            # Pick a chord tone cyclically: root → 3rd → 5th → root...
            tone = chord_intervals[slot_idx % len(chord_intervals)]
            # Target absolute pitch = chord_root + tone. Express as shift from source.
            target_semi = (chord_root + tone) % 12
            shift = _shortest_shift(source_root, target_semi)
            # Cap at ±5 (formant-safe ceiling)
            if shift > 5:
                shift = 5
            elif shift < -5:
                shift = -5
            return shift

        # ────────── Source slice picking — per-bar permutation ──────────
        def _bar_slice_order(bar_idx: int) -> list[int]:
            base = list(range(num_source_slices))
            if bar_reorder == "permuted":
                # Seed per-bar so bars differ but overall arrangement is deterministic.
                bar_rng = random.Random((seed or rng.random()) + bar_idx * 1000)
                bar_rng.shuffle(base)
            return base

        # For melody mode, pin to a CENTRAL vowel offset for consistency
        melody_source_offset_sec = 0.0
        if mode == "melody":
            # Pick the slice closest to 50% through the source (typically a
            # sustained vowel). User can improve with transient analysis later.
            melody_source_offset_sec = min(
                max(0.0, (source_length * 0.5)),
                max(0.0, source_length - seconds_per_slot_source),
            )

        # ────────── Walk bars/slots, place chops contiguously ──────────
        placements: list[dict] = []
        layer_placements: list[dict] = []

        for bar_idx in range(bars):
            bar_start_sec = bar_idx * bar_length_sec
            slice_order = _bar_slice_order(bar_idx)
            slice_cursor = 0

            for slot_idx in range(grid_per_bar):
                slot_start_sec = bar_start_sec + slot_idx * seconds_per_slot
                slot_length = seconds_per_slot  # CONTIGUOUS — no gaps

                # Source offset (in source time — accounts for playrate)
                if mode == "melody":
                    source_off_sec = melody_source_offset_sec
                else:
                    slice_idx = slice_order[slice_cursor % len(slice_order)]
                    slice_cursor += 1
                    source_off_sec = slice_idx * seconds_per_slot_source
                    # Guard against end-of-source (leave one slot worth of source)
                    max_off = max(0.0, source_length - seconds_per_slot_source)
                    if source_off_sec > max_off:
                        source_off_sec = max_off

                pitch_semis = _pitch_for_slot(bar_idx, slot_idx)
                stutter = slot_idx in stutter_slots

                # Place main chop
                try:
                    if stutter:
                        # Replace slot with 3 rapid sub-chops filling the full slot time.
                        sub_count = 3
                        sub_len = slot_length / sub_count
                        for j in range(sub_count):
                            sub_start = slot_start_sec + j * sub_len
                            res = await client.execute(
                                "chops_create_virtual_slice",
                                source_item_index=vocal_item_index,
                                target_track_index=target_track_idx,
                                target_position_sec=sub_start,
                                source_offset_sec=source_off_sec,
                                length_sec=sub_len,
                                pitch_semis=float(pitch_semis),
                                playrate=playrate,
                                fade_len_sec=0.003,
                            )
                            pdata = res.get("data", res)
                            placements.append({
                                "bar": bar_idx + 1,
                                "slot": slot_idx,
                                "sub": j,
                                "position_sec": round(sub_start, 4),
                                "length_sec": round(sub_len, 4),
                                "source_offset_sec": round(source_off_sec, 4),
                                "pitch_semis": pitch_semis,
                                "stutter": True,
                                "item_index": pdata.get("new_item_index"),
                            })
                    else:
                        res = await client.execute(
                            "chops_create_virtual_slice",
                            source_item_index=vocal_item_index,
                            target_track_index=target_track_idx,
                            target_position_sec=slot_start_sec,
                            source_offset_sec=source_off_sec,
                            length_sec=slot_length,
                            pitch_semis=float(pitch_semis),
                            playrate=playrate,
                            fade_len_sec=0.005,
                        )
                        pdata = res.get("data", res)
                        placements.append({
                            "bar": bar_idx + 1,
                            "slot": slot_idx,
                            "position_sec": round(slot_start_sec, 4),
                            "length_sec": round(slot_length, 4),
                            "source_offset_sec": round(source_off_sec, 4),
                            "pitch_semis": pitch_semis,
                            "stutter": False,
                            "item_index": pdata.get("new_item_index"),
                        })

                    # Place layer copies on separate tracks (octave / fifth)
                    for layer in layer_tracks:
                        layer_pitch = pitch_semis + layer["interval"]
                        try:
                            await client.execute(
                                "chops_create_virtual_slice",
                                source_item_index=vocal_item_index,
                                target_track_index=layer["track_index"],
                                target_position_sec=slot_start_sec,
                                source_offset_sec=source_off_sec,
                                length_sec=slot_length,
                                pitch_semis=float(layer_pitch),
                                playrate=playrate,
                                fade_len_sec=0.005,
                            )
                            layer_placements.append({
                                "bar": bar_idx + 1,
                                "slot": slot_idx,
                                "interval": layer["interval"],
                                "pitch_semis": layer_pitch,
                                "track_index": layer["track_index"],
                            })
                        except Exception:
                            pass  # layer failure is non-fatal
                except Exception as e:
                    placements.append({
                        "bar": bar_idx + 1,
                        "slot": slot_idx,
                        "error": str(e),
                    })

        # ────────── Mute original vocal ──────────
        muted_track = False
        if mute_original and vocal_track_idx >= 0:
            try:
                await client.execute(
                    "track_set_mute", track_index=vocal_track_idx, mute=True,
                )
                muted_track = True
            except Exception:
                pass

        main_chops = sum(1 for p in placements if "item_index" in p and p["item_index"] is not None)

        return {
            "style": style,
            "mode": mode,
            "bpm": bpm,
            "bars": bars,
            "bar_length_sec": round(bar_length_sec, 4),
            "grid_per_bar": grid_per_bar,
            "seconds_per_slot": round(seconds_per_slot, 4),
            "chord_count": len(chords),
            "chord_progression": chord_names,
            "source_key": source_key,
            "target_key": target_key or (chord_names[0] if chord_names else source_key),
            "uniform_shift_semis": uniform_shift,
            "pitch_warning": pitch_warning,
            "inherited_playrate": round(playrate, 4),
            "target_track_name": target_track_name,
            "target_track_index": target_track_idx,
            "layer_tracks": layer_tracks,
            "source_vocal_track_index": vocal_track_idx,
            "source_vocal_muted": muted_track,
            "source_file": source_file,
            "source_length_sec": round(source_length, 4),
            "placements_made": main_chops,
            "layer_placements_made": len(layer_placements),
            "failed_chords": failed_chords,
            "placements": placements,
            "hint": (
                f"{style}/{mode} chop built — {main_chops} contiguous chops "
                f"on '{target_track_name}', +{len(layer_placements)} layer hits "
                f"across {len(layer_tracks)} stack track(s). Uniform transpose "
                f"{uniform_shift:+d} semitones. Set REAPER pitch mode to élastique "
                f"Pro Soloist Monophonic for clean formant. Hit play."
            ),
        }

    @mcp.tool()
    async def stack_chop_layers(
        item_indices: str,
        intervals_semitones: str = "[7, 12]",
    ) -> dict:
        """For each chop, create overlay copies at parallel pitch intervals.

        The classic "future bass / Porter Robinson" harmonized chop stack:
        each chop becomes a 3-voice cluster — original (root) + 5th
        (`+7`) + octave (`+12`).

        Each layer is a clone placed at the EXACT same position as the
        source on the SAME track, with `take_set_pitch` applied. This
        means layers play simultaneously with the original.

        Args:
            item_indices: JSON array of chop indices to stack. Up to 50.
            intervals_semitones: JSON array of pitch shifts to add. Default
                                 `"[7, 12]"` = perfect 5th + octave (the
                                 classic stack). For unison-only set to
                                 `"[]"` (no extra layers).

        Note: stacking creates many overlapping items. Best applied to a
        SUBSET of chops (e.g., the standout chops in your sequence) rather
        than every chop, or REAPER's mixer will get crowded.
        """
        try:
            indices = json.loads(item_indices)
        except json.JSONDecodeError as e:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, f"item_indices: {e.msg}")
        if not isinstance(indices, list) or not indices:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "item_indices must be a non-empty JSON array")
        if len(indices) > 50:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_indices max length is 50 (avoid mixer overload)")
        try:
            intervals = json.loads(intervals_semitones)
        except json.JSONDecodeError as e:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, f"intervals_semitones: {e.msg}")
        if not isinstance(intervals, list):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "intervals_semitones must be a JSON array")
        for v in intervals:
            if not isinstance(v, (int, float)) or not -36 <= v <= 36:
                raise ReaperMCPError(
                    ErrorCode.VALUE_OUT_OF_RANGE,
                    f"interval must be a number in [-36, 36], got {v!r}",
                )

        layers_created = []
        errors = []
        for idx in indices:
            # Get source position so we can clone overlaying it
            info = await client.execute("item_get_info", item_index=idx)
            d = info.get("data", info)
            src_pos = float(d.get("position", 0))
            src_pitch = float(d.get("pitch", 0))

            for interval in intervals:
                if interval == 0:
                    continue  # no-op, the original is already at +0
                try:
                    clone_result = await client.execute(
                        "item_clone_to_position",
                        source_item_index=idx,
                        target_position_sec=src_pos,
                        target_track_index=-1,  # same track
                    )
                    cd = clone_result.get("data", clone_result)
                    new_idx = cd.get("new_item_index")
                    if new_idx is None or new_idx < 0:
                        errors.append({
                            "source_item_index": idx,
                            "interval": interval,
                            "error": f"clone returned no index: {clone_result}",
                        })
                        continue
                    new_idx = int(new_idx)
                    # Layer pitch = original take pitch + interval
                    target_pitch = src_pitch + interval
                    await client.execute(
                        "take_set_pitch",
                        item_index=new_idx,
                        semitones=target_pitch,
                        take_index=-1,
                    )
                    layers_created.append({
                        "source_item_index": idx,
                        "layer_item_index": new_idx,
                        "interval_semis": interval,
                        "final_pitch_semis": target_pitch,
                    })
                except Exception as e:
                    errors.append({
                        "source_item_index": idx,
                        "interval": interval,
                        "error": str(e),
                    })

        return {
            "source_chops": len(indices),
            "intervals_added": [v for v in intervals if v != 0],
            "layers_created": len(layers_created),
            "details": layers_created,
            "errors": errors,
            "hint": (
                f"Stacked {len(layers_created)} layer(s) across {len(indices)} chop(s). "
                f"Layers overlay at the same position so they sound together. "
                f"Hit play. If too dense, undo and use a smaller subset of chops."
            ),
        }
