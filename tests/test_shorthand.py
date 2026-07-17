"""Tests for reaper_mcp/shorthand.py — the compact composition notation parser.

Pure Python, no REAPER/IPC dependency — runs anywhere.
"""

import pytest

from reaper_mcp.shorthand import parse_shorthand, is_shorthand, _note_to_midi


# ───────────────────────── note name → MIDI ─────────────────────────

class TestNoteToMidi:
    def test_middle_c(self):
        assert _note_to_midi("C4") == 60

    def test_docstring_examples(self):
        # These exact examples are asserted in shorthand.py's own module
        # docstring — if this test ever fails, the docstring is now wrong too.
        assert _note_to_midi("D3") == 50
        assert _note_to_midi("Bb2") == 46
        assert _note_to_midi("F#5") == 78

    def test_octave_boundaries(self):
        assert _note_to_midi("C-1") == 0
        assert _note_to_midi("G9") == 127

    def test_sharp_and_flat_equivalence(self):
        assert _note_to_midi("C#4") == _note_to_midi("Db4")

    def test_lowercase_note_letter(self):
        assert _note_to_midi("c4") == 60

    def test_empty_name_raises(self):
        with pytest.raises(ValueError):
            _note_to_midi("")

    def test_unknown_letter_raises(self):
        with pytest.raises(ValueError):
            _note_to_midi("H4")

    def test_invalid_octave_raises(self):
        with pytest.raises(ValueError):
            _note_to_midi("Cx")

    def test_out_of_midi_range_raises(self):
        with pytest.raises(ValueError):
            _note_to_midi("C10")  # 12*(10+1) = 132, > 127
        with pytest.raises(ValueError):
            _note_to_midi("C-2")  # 12*(-2+1) = -12, < 0


# ───────────────────────── note/rest/chord/keyswitch parsing ─────────────────────────

class TestParseNotes:
    def test_single_note_timing(self):
        tracks = parse_shorthand("0|C4:2.0:80")
        assert len(tracks) == 1
        notes = tracks[0]["notes"]
        assert len(notes) == 1
        assert notes[0] == {"pitch": 60, "velocity": 80, "start": 0.0, "end": 2.0}

    def test_sequential_notes_advance_clock(self):
        tracks = parse_shorthand("0|C4:2.0:80 D4:1.0:70")
        notes = tracks[0]["notes"]
        assert notes[0]["start"] == 0.0 and notes[0]["end"] == 2.0
        assert notes[1]["start"] == 2.0 and notes[1]["end"] == 3.0

    def test_rest_advances_clock_without_a_note(self):
        tracks = parse_shorthand("0|C4:1.0:80 r:1.5 D4:1.0:70")
        notes = tracks[0]["notes"]
        assert len(notes) == 2
        assert notes[1]["start"] == 2.5

    def test_time_jump(self):
        tracks = parse_shorthand("0|C4:1.0:80 @10.0 D4:1.0:70")
        notes = tracks[0]["notes"]
        assert notes[1]["start"] == 10.0

    def test_chord_notes_share_start_time(self):
        tracks = parse_shorthand("0|C4:2.0:80+E4:2.0:80+G4:2.0:80")
        notes = tracks[0]["notes"]
        assert len(notes) == 3
        assert all(n["start"] == 0.0 for n in notes)
        assert {n["pitch"] for n in notes} == {60, 64, 67}

    def test_chord_clock_advances_by_longest_note(self):
        # Chord with mismatched durations — clock should advance by the max,
        # not the first note's duration, so the next event doesn't overlap.
        tracks = parse_shorthand("0|C4:1.0:80+E4:3.0:80 G4:1.0:80")
        notes = tracks[0]["notes"]
        g_note = next(n for n in notes if n["pitch"] == 67)
        assert g_note["start"] == 3.0

    def test_keyswitch_does_not_advance_clock(self):
        tracks = parse_shorthand("0|ks:0 C4:1.0:80")
        notes = tracks[0]["notes"]
        ks, note = notes[0], notes[1]
        assert ks["pitch"] == 0
        assert ks["end"] - ks["start"] == pytest.approx(0.1)
        assert note["start"] == 0.0  # keyswitch didn't push the real note later

    def test_keyswitch_out_of_range_raises(self):
        with pytest.raises(ValueError):
            parse_shorthand("0|ks:200")

    def test_malformed_note_token_raises(self):
        with pytest.raises(ValueError):
            parse_shorthand("0|C4:2.0")  # missing velocity segment

    def test_velocity_out_of_range_raises(self):
        with pytest.raises(ValueError):
            parse_shorthand("0|C4:2.0:200")

    def test_zero_duration_raises(self):
        with pytest.raises(ValueError):
            parse_shorthand("0|C4:0:80")


# ───────────────────────── line/track parsing ─────────────────────────

class TestParseShorthandStructure:
    def test_missing_pipe_raises(self):
        with pytest.raises(ValueError):
            parse_shorthand("0 C4:2.0:80")

    def test_non_integer_track_index_raises(self):
        with pytest.raises(ValueError):
            parse_shorthand("x|C4:2.0:80")

    def test_negative_track_index_raises(self):
        with pytest.raises(ValueError):
            parse_shorthand("-1|C4:2.0:80")

    def test_comment_lines_skipped(self):
        tracks = parse_shorthand("# a comment\n0|C4:2.0:80")
        assert len(tracks) == 1

    def test_blank_lines_skipped(self):
        tracks = parse_shorthand("\n\n0|C4:2.0:80\n\n")
        assert len(tracks) == 1

    def test_multiple_lines_same_track_merge(self):
        tracks = parse_shorthand("0|C4:1.0:80\n0|D4:1.0:80")
        assert len(tracks) == 1
        assert len(tracks[0]["notes"]) == 2

    def test_multiple_tracks_stay_separate(self):
        tracks = parse_shorthand("0|C4:1.0:80\n1|D4:1.0:80")
        assert len(tracks) == 2
        assert {t["track_index"] for t in tracks} == {0, 1}


# ───────────────────────── dynamics / CC ramps ─────────────────────────

class TestParseCCs:
    def test_no_ccs_specified_still_generates_fade_and_cc11(self):
        tracks = parse_shorthand("0|C4:4.0:80")
        ccs = tracks[0]["ccs"]
        assert any(c["cc_number"] == 1 for c in ccs)
        assert any(c["cc_number"] == 11 for c in ccs)

    def test_dynamic_marking_generates_cc1_and_cc11(self):
        tracks = parse_shorthand("0|C4:10.0:80|mf:0-10")
        ccs = tracks[0]["ccs"]
        cc1 = [c for c in ccs if c["cc_number"] == 1]
        cc11 = [c for c in ccs if c["cc_number"] == 11]
        assert cc1 and cc11
        # mf maps to CC1=100 (see _DYNAMICS) — final ramp point should hit it.
        assert cc1[-1]["cc_value"] == 100

    def test_raw_cc_ramp(self):
        tracks = parse_shorthand("0|C4:16.0:80|cc1:0-16:35-112")
        cc1 = [c for c in tracks[0]["ccs"] if c["cc_number"] == 1]
        assert cc1[0]["cc_value"] == 35
        assert cc1[-1]["cc_value"] == 112

    def test_cc_values_clamped_to_midi_range(self):
        tracks = parse_shorthand("0|C4:2.0:80|cc1:0-2:0-200")
        cc1 = [c for c in tracks[0]["ccs"] if c["cc_number"] == 1]
        assert all(0 <= c["cc_value"] <= 127 for c in cc1)

    def test_unknown_cc_tag_raises(self):
        with pytest.raises(ValueError):
            parse_shorthand("0|C4:2.0:80|bogus:0-2")

    def test_cc_number_out_of_range_raises(self):
        with pytest.raises(ValueError):
            parse_shorthand("0|C4:2.0:80|cc200:0-2:0-100")


# ───────────────────────── shorthand detection ─────────────────────────

class TestIsShorthand:
    def test_detects_shorthand(self):
        assert is_shorthand("0|C4:2.0:80") is True

    def test_rejects_json_array(self):
        assert is_shorthand('[{"track_index": 0}]') is False

    def test_rejects_json_object(self):
        assert is_shorthand('{"track_index": 0}') is False

    def test_rejects_plain_text_without_pipe(self):
        assert is_shorthand("just some text") is False

    def test_empty_string_is_not_shorthand(self):
        assert is_shorthand("") is False
