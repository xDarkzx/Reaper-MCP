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


from reaper_mcp_shared.plugin_cache import sanitize_plugin_name


class TestSanitizePluginName:
    def test_strips_punctuation_and_lowercases(self):
        assert sanitize_plugin_name("VST3: Pro-Q 3 (FabFilter)") == "vst3_pro_q_3_fabfilter"

    def test_collapses_repeated_separators(self):
        assert sanitize_plugin_name("A -- B") == "a_b"

    def test_no_leading_or_trailing_underscore(self):
        assert sanitize_plugin_name("  ReaEQ  ") == "reaeq"


from reaper_mcp_shared.plugin_cache import infer_curve


class TestInferCurve:
    def test_logarithmic_frequency(self):
        curve, unit = infer_curve(["20 Hz", "632 Hz", "20 kHz"])
        assert curve == "logarithmic"
        assert unit == "Hz"

    def test_linear_percentage(self):
        curve, unit = infer_curve(["0 %", "50 %", "100 %"])
        assert curve == "linear"
        assert unit == "%"

    def test_linear_decibels_with_negative_values(self):
        curve, unit = infer_curve(["-24.0 dB", "-12.0 dB", "0.0 dB"])
        assert curve == "linear"
        assert unit == "dB"

    def test_stepped_enum_returns_stepped(self):
        curve, unit = infer_curve(["Off", "Low", "High"])
        assert curve == "stepped"
        assert unit is None

    def test_mixed_numeric_and_text_is_unknown(self):
        curve, unit = infer_curve(["0 %", "Bypass", "100 %"])
        assert curve == "unknown"

    def test_constant_value_is_unknown_not_a_crash(self):
        curve, unit = infer_curve(["0 dB", "0 dB", "0 dB"])
        assert curve == "unknown"


import pytest

from reaper_mcp_shared import constants as _constants
from reaper_mcp_shared.plugin_cache import load_cached_map, save_cached_map


@pytest.fixture
def plugin_map_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(_constants, "PLUGIN_MAP_DIR", str(tmp_path / "plugin_maps"))
    monkeypatch.setattr("reaper_mcp_shared.plugin_cache.PLUGIN_MAP_DIR", str(tmp_path / "plugin_maps"))
    return str(tmp_path / "plugin_maps")


class TestCacheRoundTrip:
    def test_save_then_load_returns_same_params(self, plugin_map_dir):
        params = [{"index": 0, "name": "Freq", "samples": ["20 Hz", "632 Hz", "20 kHz"],
                   "inferred_curve": "logarithmic", "inferred_unit": "Hz"}]
        save_cached_map("Test Plugin", params, truncated=False)

        loaded = load_cached_map("Test Plugin")
        assert loaded["plugin_name"] == "Test Plugin"
        assert loaded["truncated"] is False
        assert loaded["params"] == params
        assert "scanned_at" in loaded

    def test_load_missing_plugin_returns_none(self, plugin_map_dir):
        assert load_cached_map("Never Scanned Plugin") is None

    def test_load_corrupt_file_returns_none_not_raise(self, plugin_map_dir):
        os.makedirs(plugin_map_dir, exist_ok=True)
        from reaper_mcp_shared.plugin_cache import sanitize_plugin_name
        path = os.path.join(plugin_map_dir, sanitize_plugin_name("Broken") + ".json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        assert load_cached_map("Broken") is None

    def test_save_creates_directory_if_missing(self, plugin_map_dir):
        assert not os.path.isdir(plugin_map_dir)
        save_cached_map("Any Plugin", [], truncated=False)
        assert os.path.isdir(plugin_map_dir)
