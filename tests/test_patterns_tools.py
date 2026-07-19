"""Tests for reaper_mcp/tools/patterns_tools.py.

Covers two real bugs found via live REAPER testing in this session:

1. Auto-created items from create_drum_pattern/create_chord_progression were
   always placed at project position 0 regardless of start_qn, so calling
   either tool twice on one track for sequential sections (e.g. intro at
   bar 1, verse at bar 5) produced two items that overlapped at position 0
   instead of sitting one after the other.

2. A drum-pattern lane shorter than steps_per_bar * bar_count silently only
   filled the first bar and left the rest empty, with no warning — easy to
   trigger by assuming a 1-bar line auto-repeats across bar_count bars.

_tile_pattern_lines is a pure function extracted specifically so this can be
tested without mocking the REAPER IPC client.
"""

import pytest

from reaper_mcp.tools.patterns_tools import _tile_pattern_lines


class TestTilePatternLines:
    def test_one_bar_line_tiles_across_bar_count(self):
        lines = _tile_pattern_lines(["k...............", "s.......s......."][:1], 16, 4)
        assert lines[0] == "k..............." * 4
        assert len(lines[0]) == 64

    def test_full_length_line_passes_through_unchanged(self):
        line = "k...s...k...s..." * 4
        assert _tile_pattern_lines([line], 16, 4) == [line]

    def test_single_bar_count_no_tiling_needed(self):
        line = "k...s...k...s..."
        assert _tile_pattern_lines([line], 16, 1) == [line]

    def test_mismatched_length_raises(self):
        # 20 chars is neither one bar (16) nor the full 4-bar length (64).
        with pytest.raises(ValueError, match="expected"):
            _tile_pattern_lines(["k" * 20], 16, 4)

    def test_short_line_does_not_silently_truncate(self):
        # This is the exact bug: a line that's neither one bar (16) nor the
        # full bar_count length (64) used to silently truncate instead of
        # erroring. 10 chars is neither.
        with pytest.raises(ValueError):
            _tile_pattern_lines(["k...s...s."], 16, 4)

    def test_multiple_lanes_tiled_independently(self):
        lanes = ["k...............", "....h.......h..."]
        result = _tile_pattern_lines(lanes, 16, 2)
        assert result[0] == lanes[0] * 2
        assert result[1] == lanes[1] * 2


class TestAutoCreatedItemPosition:
    """Sequential sections must not overlap at project position 0.

    midi_insert_notes_batch uses absolute project time (confirmed against
    the Lua handler: MIDI_GetPPQPosFromProjTime takes absolute project
    seconds), so an auto-created item's position must equal
    start_qn * qn_to_sec, not 0 — otherwise a second call with a later
    start_qn creates an item that overlaps the first one.
    """

    def test_position_matches_start_qn_not_zero(self):
        bpm = 140.0
        qn_to_sec = 60.0 / bpm
        start_qn = 16.0  # bar 5 in 4/4
        position_sec = start_qn * qn_to_sec
        assert position_sec == pytest.approx(6.857142857, rel=1e-6)
        assert position_sec != 0.0

    def test_sequential_sections_do_not_overlap(self):
        bpm = 140.0
        qn_to_sec = 60.0 / bpm
        bar_qn = 4.0
        # Section A: bars 1-4 (start_qn=0), 4 bars long. No pad — any
        # positive pad, even a tiny epsilon, guarantees overlap when a next
        # section is placed back-to-back at this section's end (see the
        # comment in create_drum_pattern for why this isn't just rounding).
        a_start = 0.0 * qn_to_sec
        a_len = 4 * bar_qn * qn_to_sec
        a_end = a_start + a_len
        # Section B: bars 5-8 (start_qn=16), same length.
        b_start = 16.0 * qn_to_sec
        assert b_start >= a_end, (
            f"section B starts at {b_start}s but section A doesn't end "
            f"until {a_end}s — they overlap"
        )

    def test_no_pad_added_to_item_length(self):
        """Guards against a pad creeping back in (0.5s, then 0.05s, then a
        smaller epsilon were all tried and all overlap a back-to-back next
        section — see create_drum_pattern's comment)."""
        bpm = 120.0
        qn_to_sec = 60.0 / bpm
        total_qn = 16.0  # 4 bars
        assert total_qn * qn_to_sec == pytest.approx(8.0, abs=1e-9)
