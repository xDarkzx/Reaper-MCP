"""Demo / test scaffolding — spawn a minimal project to verify mix pipelines.

One call creates ~8 named tracks with REAPER's stock ReaSynth on each plus a
short MIDI pattern, so you can run `engine_mix(style)` and `engine_master(style)`
and actually hear the result.

Uses only stock REAPER plugins — works out of the box on any install.
"""

import json
import logging

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode

logger = logging.getLogger(__name__)


# 8-bar patterns per role — all at 140 BPM. Shorthand would be nicer but
# midi_insert_notes_batch gives exact control and avoids shorthand quirks.
# Times are in seconds at 140 BPM: 1 beat = 60/140 = 0.4286s, bar = 1.7143s.
_BPM = 140.0
_BEAT = 60.0 / _BPM
_BAR = 4 * _BEAT
_EIGHT_BARS = 8 * _BAR  # ~13.71s


def _beats(n: float) -> float:
    return n * _BEAT


def _note(pitch: int, start: float, duration: float, velocity: int = 100, channel: int = 0) -> dict:
    return {
        "pitch": pitch,
        "velocity": velocity,
        "start": round(start, 4),
        "end": round(start + duration, 4),
        "channel": channel,
    }


def _pattern_kick() -> list[dict]:
    """4-on-the-floor: C2 on every beat for 8 bars."""
    notes = []
    for bar in range(8):
        for beat in range(4):
            t = bar * _BAR + beat * _BEAT
            notes.append(_note(36, t, _BEAT * 0.5, velocity=115))
    return notes


def _pattern_snare() -> list[dict]:
    """Backbeat: D2 on beats 2 and 4."""
    notes = []
    for bar in range(8):
        for beat in (1, 3):
            t = bar * _BAR + beat * _BEAT
            notes.append(_note(38, t, _BEAT * 0.3, velocity=105))
    return notes


def _pattern_hats() -> list[dict]:
    """Closed hi-hat 16ths, slight velocity variance."""
    notes = []
    for bar in range(8):
        for sixteenth in range(16):
            t = bar * _BAR + sixteenth * (_BEAT / 4)
            vel = 70 if sixteenth % 2 else 90  # off-beats softer
            notes.append(_note(42, t, _BEAT * 0.1, velocity=vel))
    return notes


def _pattern_sub() -> list[dict]:
    """Sub bass: half-note root (A1 → C2 chord progression)."""
    roots = [33, 33, 36, 36, 33, 33, 31, 31]  # A1 A1 C2 C2 A1 A1 G1 G1
    notes = []
    for bar, root in enumerate(roots):
        notes.append(_note(root, bar * _BAR, _BAR * 0.95, velocity=100))
    return notes


def _pattern_pad() -> list[dict]:
    """Sustained triads (A min, C maj, A min, G maj)."""
    chords = [
        (57, 60, 64),  # A3 C4 E4 — A min
        (57, 60, 64),
        (60, 64, 67),  # C4 E4 G4 — C maj
        (60, 64, 67),
        (57, 60, 64),
        (57, 60, 64),
        (55, 59, 62),  # G3 B3 D4 — G maj
        (55, 59, 62),
    ]
    notes = []
    for bar, chord in enumerate(chords):
        for p in chord:
            notes.append(_note(p, bar * _BAR, _BAR * 0.98, velocity=70))
    return notes


def _pattern_lead() -> list[dict]:
    """Simple melody line."""
    # Sequence of (pitch, start_beat, duration_beats)
    seq = [
        (72, 0, 2), (76, 2, 1), (74, 3, 1),      # bar 1
        (72, 4, 2), (69, 6, 2),                    # bar 2
        (74, 8, 2), (76, 10, 2),                   # bar 3
        (79, 12, 3), (76, 15, 1),                  # bar 4
        (72, 16, 2), (76, 18, 1), (74, 19, 1),     # bar 5
        (72, 20, 2), (69, 22, 2),                  # bar 6
        (74, 24, 2), (72, 26, 2),                  # bar 7
        (76, 28, 4),                                # bar 8 (hold)
    ]
    return [_note(p, _beats(s), _beats(d), velocity=95) for p, s, d in seq]


def _pattern_vocal_chop() -> list[dict]:
    """Sparse pitched vocal chops — eighth-note stabs on beats 1 and 3."""
    notes = []
    pitches = [64, 64, 67, 67, 64, 64, 62, 62]  # E4 E4 G4 G4 E4 E4 D4 D4
    for bar, p in enumerate(pitches):
        notes.append(_note(p, bar * _BAR + 0, _BEAT * 0.3, velocity=80))
        notes.append(_note(p, bar * _BAR + 2 * _BEAT, _BEAT * 0.3, velocity=80))
    return notes


DEMO_TRACKS = [
    ("Kick Drum",  _pattern_kick),
    ("Snare",      _pattern_snare),
    ("Closed Hat", _pattern_hats),
    ("Sub Bass",   _pattern_sub),
    ("Pad",        _pattern_pad),
    ("Lead Synth", _pattern_lead),
    ("Vocal Chop", _pattern_vocal_chop),
]


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def demo_edm_project(clean_first: bool = True, bpm: float = 140.0) -> dict:
        """Scaffold a minimal EDM test project with 7 tracks, ReaSynth on each, and 8 bars of MIDI.

        Use this to verify `engine_mix` / `engine_master` / `setup_sidechain` actually
        work end-to-end: after this call, you should immediately be able to run:

            engine_mix("melodic_dubstep")    # applies EQ/comp/reverb/sidechain
            engine_master("melodic_dubstep") # master chain on master bus
            transport_play()                  # hear it

        Tracks created: Kick Drum, Snare, Closed Hat, Sub Bass, Pad, Lead Synth, Vocal Chop.
        Each gets REAPER's stock ReaSynth (always available) + a simple 8-bar pattern.

        Args:
            clean_first: Wipe existing MIDI + markers first (default True).
            bpm: Project BPM (default 140 — matches melodic_dubstep's half-time feel).
        """
        results = {"tracks_created": 0, "midi_items_created": 0, "total_notes": 0, "errors": []}

        if clean_first:
            try:
                await client.execute("wipe_all_midi")
            except Exception as e:
                results["errors"].append(f"wipe_all_midi failed: {e}")

        await client.execute("transport_set_bpm", bpm=bpm)

        # Discover existing track count so we can append vs insert
        live = await client.execute("track_get_all")
        live_data = live.get("data", live)
        existing = live_data.get("tracks", [])
        start_offset = len(existing)

        for i, (name, pattern_fn) in enumerate(DEMO_TRACKS):
            track_index = start_offset + i

            # Create the track
            try:
                await client.execute("track_create", name=name)
                results["tracks_created"] += 1
            except Exception as e:
                results["errors"].append(f"track_create {name!r}: {e}")
                continue

            # Add ReaSynth as the instrument (stock — always installed)
            try:
                await client.execute("fx_add", track_index=track_index, fx_name="ReaSynth")
            except Exception as e:
                results["errors"].append(f"fx_add ReaSynth on {name!r}: {e}")

            # Create an empty MIDI item spanning the 8 bars
            try:
                item_result = await client.execute(
                    "item_create_midi",
                    track_index=track_index,
                    position=0.0,
                    length=_EIGHT_BARS,
                )
                item_data = item_result.get("data", item_result)
                # Lua returns the item's global "index" field (build_item_info)
                item_index = item_data.get("index")
                if item_index is None:
                    results["errors"].append(f"item_create_midi {name!r}: no 'index' returned: {item_data}")
                    continue
                results["midi_items_created"] += 1
            except Exception as e:
                results["errors"].append(f"item_create_midi on {name!r}: {e}")
                continue

            # Insert the pattern's notes
            notes = pattern_fn()
            try:
                await client.execute(
                    "midi_insert_notes_batch",
                    track_index=track_index,
                    item_index=item_index,
                    notes=json.dumps(notes),
                )
                results["total_notes"] += len(notes)
            except Exception as e:
                results["errors"].append(f"midi_insert_notes_batch {name!r}: {e}")

        results["bpm"] = bpm
        results["duration_seconds"] = _EIGHT_BARS
        results["next_steps"] = [
            "engine_mix('melodic_dubstep')    # apply mix pipeline",
            "engine_master('melodic_dubstep') # apply mastering",
            "transport_set_position(position=0)",
            "transport_play()                  # hear result",
        ]
        return results
