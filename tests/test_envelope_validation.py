"""Tests for envelope_tools validation — _validate_envelope_value and _validate_gain_batch.

Pure logic only — no REAPER/IPC dependency needed, matching the pattern
tests/test_item_tools.py already uses for _validate_items_apply_entries.
"""

import pytest

from reaper_mcp.tools.envelope_tools import (
    _validate_envelope_value,
    _validate_gain_batch,
)
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


class TestValidateEnvelopeValue:
    """Per-point validation — _validate_envelope_value."""

    def test_gain_unity_passes(self):
        _validate_envelope_value(1.0, "Volume", False, 0)

    def test_gain_zero_passes(self):
        _validate_envelope_value(0.0, "Volume", False, 0)

    def test_gain_above_unity_passes(self):
        _validate_envelope_value(2.0, "Volume", False, 0)

    def test_gain_half_passes(self):
        _validate_envelope_value(0.5, "Volume", False, 0)

    def test_gain_negative_raises(self):
        with pytest.raises(ReaperMCPError) as exc_info:
            _validate_envelope_value(-6.0, "Volume", False, 0)
        assert exc_info.value.code == ErrorCode.VALUE_OUT_OF_RANGE
        assert "Do NOT clamp negative dB to 0.0" in str(exc_info.value)

    def test_gain_pre_fx_negative_raises(self):
        with pytest.raises(ReaperMCPError):
            _validate_envelope_value(-3.0, "Volume (Pre-FX)", False, 0)

    def test_width_negative_raises(self):
        with pytest.raises(ReaperMCPError):
            _validate_envelope_value(-1.0, "Width", False, 0)

    def test_pan_in_range_passes(self):
        _validate_envelope_value(0.5, "Pan", False, 0)

    def test_pan_hard_left_passes(self):
        _validate_envelope_value(-1.0, "Pan", False, 0)

    def test_pan_hard_right_passes(self):
        _validate_envelope_value(1.0, "Pan", False, 0)

    def test_pan_out_of_range_raises(self):
        with pytest.raises(ReaperMCPError) as exc_info:
            _validate_envelope_value(1.5, "Pan", False, 0)
        assert exc_info.value.code == ErrorCode.VALUE_OUT_OF_RANGE

    def test_mute_zero_passes(self):
        _validate_envelope_value(0.0, "Mute", False, 0)

    def test_mute_one_passes(self):
        _validate_envelope_value(1.0, "Mute", False, 0)

    def test_mute_half_raises(self):
        with pytest.raises(ReaperMCPError):
            _validate_envelope_value(0.5, "Mute", False, 0)

    def test_fx_param_zero_passes(self):
        _validate_envelope_value(0.0, "Volume", True, 0)

    def test_fx_param_one_passes(self):
        _validate_envelope_value(1.0, "Volume", True, 0)

    def test_fx_param_out_of_range_raises(self):
        with pytest.raises(ReaperMCPError) as exc_info:
            _validate_envelope_value(1.1, "Volume", True, 0)
        assert exc_info.value.code == ErrorCode.VALUE_OUT_OF_RANGE

    def test_fx_param_negative_raises(self):
        with pytest.raises(ReaperMCPError):
            _validate_envelope_value(-0.1, "Volume", True, 0)


class TestValidateGainBatch:
    """Batch all-zero guard — _validate_gain_batch (issue #39)."""

    def test_all_zero_multi_point_raises(self):
        pts = [{"time": i * 0.5, "value": 0.0} for i in range(8)]
        with pytest.raises(ReaperMCPError) as exc_info:
            _validate_gain_batch(pts, "Volume")
        assert exc_info.value.code == ErrorCode.VALUE_OUT_OF_RANGE

    def test_single_zero_point_passes(self):
        _validate_gain_batch([{"time": 5.0, "value": 0.0}], "Volume")

    def test_two_zero_points_raises(self):
        with pytest.raises(ReaperMCPError):
            _validate_gain_batch(
                [{"time": 0.0, "value": 0.0}, {"time": 1.0, "value": 0.0}],
                "Volume",
            )

    def test_mixed_batch_passes(self):
        pts = [
            {"time": 0.0, "value": 1.0},
            {"time": 1.0, "value": 0.5},
            {"time": 2.0, "value": 0.0},
        ]
        _validate_gain_batch(pts, "Volume")

    def test_uniform_non_zero_passes(self):
        pts = [{"time": i * 0.5, "value": 1.0} for i in range(10)]
        _validate_gain_batch(pts, "Volume")

    def test_pan_all_zero_passes(self):
        pts = [{"time": i * 0.5, "value": 0.0} for i in range(4)]
        _validate_gain_batch(pts, "Pan")

    def test_mute_all_zero_passes(self):
        pts = [{"time": i * 1.0, "value": 0.0} for i in range(3)]
        _validate_gain_batch(pts, "Mute")

    def test_width_pre_fx_all_zero_raises(self):
        pts = [{"time": i * 0.5, "value": 0.0} for i in range(4)]
        with pytest.raises(ReaperMCPError):
            _validate_gain_batch(pts, "Width (Pre-FX)")

    def test_volume_pre_fx_all_zero_raises(self):
        pts = [{"time": i * 0.5, "value": 0.0} for i in range(4)]
        with pytest.raises(ReaperMCPError):
            _validate_gain_batch(pts, "Volume (Pre-FX)")
