"""Tests for reaper_mcp/tools/project_tools.py.

_resolve_render_output is a pure function (no REAPER/IPC mocking needed),
extracted from project_export_audio so the directory-splitting and
stems-vs-master filename-pattern selection is directly testable.
"""

import os

from reaper_mcp_shared.constants import ALLOWED_EXPORT_FORMATS
from reaper_mcp.tools.project_tools import _resolve_render_output, _RENDER_FORMAT_CODES


class TestResolveRenderOutput:
    def test_master_uses_paths_own_filename(self):
        # Built with os.path.join instead of a hardcoded separator so this
        # exercises the real split behavior on whatever OS runs it — a
        # literal Windows path (backslashes) passed CI on Windows locally
        # but failed on Linux/macOS, where os.path treats '\' as a plain
        # character, not a separator, so the whole string reads as one
        # filename with no directory component.
        path = os.path.join("Mixes", "song_final.wav")
        directory, pattern = _resolve_render_output(path, source="master", pattern="")
        assert directory == "Mixes"
        assert pattern == "song_final.wav"

    def test_stems_ignores_filename_uses_pattern(self):
        path = os.path.join("Mixes", "ignored.wav")
        directory, pattern = _resolve_render_output(path, source="stems", pattern="$track")
        assert directory == "Mixes"
        assert pattern == "$track"

    def test_stems_with_no_pattern_defaults_to_dollar_track(self):
        path = os.path.join("Mixes", "ignored.wav")
        directory, pattern = _resolve_render_output(path, source="stems", pattern="")
        assert pattern == "$track"

    def test_path_with_no_directory_component_defaults_to_dot(self):
        directory, pattern = _resolve_render_output(
            "song.wav", source="master", pattern="",
        )
        assert directory == "."
        assert pattern == "song.wav"

    def test_forward_slash_path(self):
        directory, pattern = _resolve_render_output(
            "/home/user/mixes/song.wav", source="master", pattern="",
        )
        assert directory == "/home/user/mixes"
        assert pattern == "song.wav"


class TestRenderFormatCodes:
    def test_covers_every_allowed_export_format(self):
        # These two sets must stay in sync — a format ALLOWED_EXPORT_FORMATS
        # accepts but _RENDER_FORMAT_CODES doesn't map would pass validation
        # and then fail deep inside the Lua render call instead.
        assert set(_RENDER_FORMAT_CODES.keys()) == ALLOWED_EXPORT_FORMATS

    def test_wav_and_flac_and_aiff_codes(self):
        # Byte-reversed from the format's own fourCC — confirmed empirically
        # against a live REAPER instance (the forward form ("wave") errored
        # with "invalid format" when written via RENDER_FORMAT).
        assert _RENDER_FORMAT_CODES["wav"] == "evaw"
        assert _RENDER_FORMAT_CODES["flac"] == "calf"
        assert _RENDER_FORMAT_CODES["aiff"] == "ffia"
