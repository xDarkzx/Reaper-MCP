"""Tests for reaper_mcp_shared/plugin_cache.py — the VST param auto-scan cache.

Pure filesystem/string logic, no REAPER/IPC needed (mirrors test_command_history.py).
"""

import os

from reaper_mcp_shared.constants import PLUGIN_MAP_DIR, MAX_SCAN_PARAMS


class TestConstants:
    def test_plugin_map_dir_is_under_reaper_mcp_shared(self):
        assert os.path.basename(PLUGIN_MAP_DIR) == "plugin_maps"

    def test_max_scan_params_is_200(self):
        assert MAX_SCAN_PARAMS == 200
