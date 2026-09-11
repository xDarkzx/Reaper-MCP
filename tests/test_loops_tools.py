"""Tests for reaper_mcp/tools/loops_tools.py's pure filter/walk logic.

Only the pure functions are tested directly (not the @mcp.tool() wrappers
themselves) — same convention as test_project_tools.py's _resolve_render_output:
importing reaper_mcp.main (which the tool wrappers pull in via `from
reaper_mcp.main import client`) has real filesystem side effects
(ensure_private_dir, history sweep) that unit tests shouldn't trigger.
"""

from pathlib import Path

from reaper_mcp.tools.loops_tools import (
    _matches_key,
    _matches_query,
    _parse_bpm,
    _parse_key,
    _parse_role,
    _passes_filters,
    _walk_subfolders,
)


class TestParseKeyBareLetter:
    """Bare major-key letters (e.g. "D" with no accidental/quality) are
    accepted, per an explicit tradeoff decision to support the very common
    "Sub_Bass_D_130.wav" naming style at the cost of occasionally
    false-matching an unrelated single-letter token (take/version/mic).
    """

    def test_bare_letter_with_boundaries_parses_as_major_key(self):
        assert _parse_key("Sub_Bass_D_130.wav") == "D"
        assert _parse_key("Lead_Vocal_D_130bpm.wav") == "D"

    def test_still_prefers_accidental_and_quality_when_present(self):
        assert _parse_key("Reese_Bass_F#m_128.wav") == "F#m"
        assert _parse_key("Ethereal_Vox_Dm_140.wav") == "Dm"

    def test_letter_without_boundary_separators_not_matched(self):
        # "Drone" contains a leading "D" but not as a separated token.
        assert _parse_key("Drone_140.wav") is None


class TestMatchesQuery:
    def test_empty_query_matches_everything(self):
        assert _matches_query("/any/path/file.wav", []) is True

    def test_single_term_matches_substring_case_insensitive(self):
        assert _matches_query("/SFX/Footsteps/Concrete_01.wav", ["footstep"]) is True

    def test_single_term_no_match(self):
        assert _matches_query("/SFX/Doors/creak.wav", ["footstep"]) is False

    def test_multiple_terms_require_all_and_semantics(self):
        path = "/SFX/Footsteps/concrete_heavy_01.wav"
        assert _matches_query(path, ["footstep", "concrete"]) is True
        assert _matches_query(path, ["footstep", "wood"]) is False

    def test_term_matches_containing_folder_not_just_filename(self):
        # The word "footstep" appears only in the folder name, not the
        # filename itself — matching the full path is the whole point.
        assert _matches_query("/SFX/Footsteps/01.wav", ["footstep"]) is True


class TestMatchesKey:
    def test_empty_filter_matches_everything(self):
        assert _matches_key("Am", "") is True

    def test_no_quality_in_filter_matches_any_quality(self):
        assert _matches_key("D", "D") is True
        assert _matches_key("Dm", "D") is True
        assert _matches_key("Dmaj", "D") is True

    def test_does_not_match_different_accidental(self):
        assert _matches_key("D#", "D") is False
        assert _matches_key("Db", "D") is False
        assert _matches_key("D#m", "D") is False

    def test_accidental_in_filter_must_match_exactly(self):
        assert _matches_key("F#m", "F#") is True
        assert _matches_key("Fm", "F#") is False

    def test_quality_in_filter_requires_matching_quality(self):
        assert _matches_key("Dm", "Dm") is True
        assert _matches_key("Dmaj", "Dm") is False

    def test_unparsed_key_fails_any_filter(self):
        assert _matches_key(None, "D") is False

    def test_case_insensitive(self):
        assert _matches_key("am", "A") is True


class TestPassesFilters:
    def _parsed(self, bpm=None, key=None, role=None):
        return {"bpm": bpm, "key": key, "role": role}

    def test_no_filters_passes(self):
        assert _passes_filters(self._parsed(), [], "/any/path.wav", 0, 0, "") is True

    def test_bpm_range_filters_out_below_min(self):
        parsed = self._parsed(bpm=100)
        assert _passes_filters(parsed, [], "/x.wav", 120, 0, "") is False

    def test_bpm_range_filters_out_above_max(self):
        parsed = self._parsed(bpm=140)
        assert _passes_filters(parsed, [], "/x.wav", 0, 130, "") is False

    def test_bpm_range_passes_within_range(self):
        parsed = self._parsed(bpm=125)
        assert _passes_filters(parsed, [], "/x.wav", 120, 130, "") is True

    def test_bpm_filter_excludes_unparsed_bpm(self):
        parsed = self._parsed(bpm=None)
        assert _passes_filters(parsed, [], "/x.wav", 120, 0, "") is False

    def test_role_filter_exact_case_insensitive(self):
        parsed = self._parsed(role="kick")
        assert _passes_filters(parsed, [], "/x.wav", 0, 0, "Kick") is True
        assert _passes_filters(parsed, [], "/x.wav", 0, 0, "snare") is False

    def test_role_filter_excludes_unparsed_role(self):
        parsed = self._parsed(role=None)
        assert _passes_filters(parsed, [], "/x.wav", 0, 0, "kick") is False

    def test_combined_query_and_bpm_and_role(self):
        parsed = self._parsed(bpm=128, role="kick")
        path = "/Techno/Kicks/kick_128bpm.wav"
        assert _passes_filters(parsed, ["techno"], path, 120, 130, "kick") is True
        assert _passes_filters(parsed, ["house"], path, 120, 130, "kick") is False

    def test_key_filter_passes_matching_key(self):
        parsed = self._parsed(key="Dm")
        assert _passes_filters(parsed, [], "/x.wav", 0, 0, "", key="D") is True

    def test_key_filter_excludes_non_matching_key(self):
        parsed = self._parsed(key="F#m")
        assert _passes_filters(parsed, [], "/x.wav", 0, 0, "", key="D") is False

    def test_key_filter_excludes_unparsed_key(self):
        parsed = self._parsed(key=None)
        assert _passes_filters(parsed, [], "/x.wav", 0, 0, "", key="D") is False


class TestWalkSubfolders:
    def _make_tree(self, tmp_path: Path) -> Path:
        (tmp_path / "Footsteps").mkdir()
        (tmp_path / "Footsteps" / "a.wav").write_bytes(b"")
        (tmp_path / "Footsteps" / "b.wav").write_bytes(b"")
        (tmp_path / "Doors").mkdir()
        (tmp_path / "Doors" / "creak.wav").write_bytes(b"")
        (tmp_path / "Doors" / "Wood").mkdir()
        (tmp_path / "Doors" / "Wood" / "open.wav").write_bytes(b"")
        (tmp_path / "Doors" / "Wood" / "notes.txt").write_bytes(b"")  # non-audio
        return tmp_path

    def test_lists_immediate_and_nested_subfolders_within_depth(self, tmp_path):
        root = self._make_tree(tmp_path)
        folders, truncated = _walk_subfolders(root, max_depth=2)
        rel_paths = {f["relative_path"] for f in folders}
        assert rel_paths == {"Footsteps", "Doors", str(Path("Doors") / "Wood")}
        assert truncated is False

    def test_max_depth_1_excludes_nested_subfolder(self, tmp_path):
        root = self._make_tree(tmp_path)
        folders, _ = _walk_subfolders(root, max_depth=1)
        rel_paths = {f["relative_path"] for f in folders}
        assert rel_paths == {"Footsteps", "Doors"}

    def test_audio_file_count_ignores_non_audio_files(self, tmp_path):
        root = self._make_tree(tmp_path)
        folders, _ = _walk_subfolders(root, max_depth=2)
        by_path = {f["relative_path"]: f["audio_file_count"] for f in folders}
        assert by_path["Footsteps"] == 2
        assert by_path[str(Path("Doors") / "Wood")] == 1  # notes.txt excluded

    def test_root_itself_not_included(self, tmp_path):
        root = self._make_tree(tmp_path)
        folders, _ = _walk_subfolders(root, max_depth=2)
        assert all(f["relative_path"] != "." for f in folders)

    def test_flat_folder_with_no_subfolders_returns_empty(self, tmp_path):
        (tmp_path / "only.wav").write_bytes(b"")
        folders, truncated = _walk_subfolders(tmp_path, max_depth=2)
        assert folders == []
        assert truncated is False


class TestScanFilterIntegrationWithParsers:
    """Sanity-check the new filters against the module's own existing
    filename parsers, not just synthetic dicts — catches a mismatch
    between what _parse_role/_parse_bpm actually return and what
    _passes_filters expects.
    """

    def test_role_filter_matches_real_parsed_role(self):
        parsed = {
            "bpm": _parse_bpm("Kick_128bpm.wav"),
            "key": None,
            "role": _parse_role("Kick_128bpm.wav"),
        }
        assert _passes_filters(parsed, [], "/x/Kick_128bpm.wav", 0, 0, "kick") is True

    def test_bpm_filter_matches_real_parsed_bpm(self):
        parsed = {
            "bpm": _parse_bpm("Deep_Sub_Bass_128.wav"),
            "key": None,
            "role": _parse_role("Deep_Sub_Bass_128.wav"),
        }
        assert _passes_filters(parsed, [], "/x/Deep_Sub_Bass_128.wav", 125, 130, "") is True
