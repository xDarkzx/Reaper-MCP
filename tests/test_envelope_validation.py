"""Tests for envelope_tools._validate_envelope_value and the envelope_add_points
batch-level all-zero guard (issue #39).

These tests exercise the validation layer only — no REAPER connection needed.
"""

import json
import pytest

from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode
from reaper_mcp.tools.envelope_tools import _validate_envelope_value


# ---------------------------------------------------------------------------
# _validate_envelope_value — per-point unit tests
# ---------------------------------------------------------------------------


class TestValidateEnvelopeValue:
    """Unit tests for _validate_envelope_value."""

    # -- Gain envelopes (Volume, Width, …) -----------------------------------

    def test_gain_envelope_unity_is_valid(self):
        """1.0 (0 dB) must pass without error."""
        _validate_envelope_value(1.0, "Volume", False, 0)

    def test_gain_envelope_zero_is_valid_single(self):
        """0.0 is valid on a per-point basis (−inf dB fade point)."""
        _validate_envelope_value(0.0, "Volume", False, 0)

    def test_gain_envelope_positive_is_valid(self):
        """Values above 1.0 (amplification) are valid."""
        _validate_envelope_value(2.0, "Volume", False, 0)

    def test_gain_envelope_half_is_valid(self):
        """0.5 ≈ −6 dB is valid."""
        _validate_envelope_value(0.5, "Volume", False, 0)

    def test_gain_envelope_negative_raises(self):
        """Negative values are raw dB — must raise VALUE_OUT_OF_RANGE."""
        with pytest.raises(ReaperMCPError) as exc_info:
            _validate_envelope_value(-6.0, "Volume", False, 0)
        assert exc_info.value.error_code == ErrorCode.VALUE_OUT_OF_RANGE
        assert "Do NOT clamp negative dB to 0.0" in str(exc_info.value)

    def test_gain_envelope_pre_fx_variant(self):
        """Volume (Pre-FX) is also a gain envelope — negative must raise."""
        with pytest.raises(ReaperMCPError):
            _validate_envelope_value(-3.0, "Volume (Pre-FX)", False, 2)

    def test_width_envelope_negative_raises(self):
        """Width is a gain envelope — negative must raise."""
        with pytest.raises(ReaperMCPError):
            _validate_envelope_value(-1.0, "Width", False, 0)

    # -- Pan envelopes -------------------------------------------------------

    def test_pan_within_range_is_valid(self):
        _validate_envelope_value(0.5, "Pan", False, 0)

    def test_pan_hard_left_is_valid(self):
        _validate_envelope_value(-1.0, "Pan", False, 0)

    def test_pan_hard_right_is_valid(self):
        _validate_envelope_value(1.0, "Pan", False, 0)

    def test_pan_out_of_range_raises(self):
        with pytest.raises(ReaperMCPError) as exc_info:
            _validate_envelope_value(1.5, "Pan", False, 0)
        assert exc_info.value.error_code == ErrorCode.VALUE_OUT_OF_RANGE

    # -- Mute envelope -------------------------------------------------------

    def test_mute_zero_is_valid(self):
        _validate_envelope_value(0.0, "Mute", False, 0)

    def test_mute_one_is_valid(self):
        _validate_envelope_value(1.0, "Mute", False, 0)

    def test_mute_half_raises(self):
        with pytest.raises(ReaperMCPError):
            _validate_envelope_value(0.5, "Mute", False, 0)

    # -- FX param envelopes --------------------------------------------------

    def test_fx_param_zero_is_valid(self):
        """0.0 is valid for FX param even if it means minimum — not a gain envelope."""
        _validate_envelope_value(0.0, "Volume", True, 0)  # is_fx_param overrides name

    def test_fx_param_one_is_valid(self):
        _validate_envelope_value(1.0, "Volume", True, 0)

    def test_fx_param_out_of_range_raises(self):
        with pytest.raises(ReaperMCPError) as exc_info:
            _validate_envelope_value(1.1, "Volume", True, 0)
        assert exc_info.value.error_code == ErrorCode.VALUE_OUT_OF_RANGE

    def test_fx_param_negative_raises(self):
        with pytest.raises(ReaperMCPError):
            _validate_envelope_value(-0.1, "Volume", True, 0)


# ---------------------------------------------------------------------------
# Batch all-zero guard — integration-style tests on the validation block
# ---------------------------------------------------------------------------


def _run_batch_guard(pts: list, envelope_name: str = "Volume", is_fx_param: bool = False):
    """Replicate only the guard logic from envelope_add_points for testing."""
    from reaper_mcp.tools.envelope_tools import _validate_envelope_value, _GAIN_ENVELOPES

    for i, pt in enumerate(pts):
        _validate_envelope_value(pt["value"], envelope_name, is_fx_param, i)

    if not is_fx_param and envelope_name in _GAIN_ENVELOPES:
        if len(pts) > 1 and all(pt.get("value", 1.0) == 0.0 for pt in pts):
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE,
                f"All {len(pts)} points have value=0.0 on a {envelope_name} envelope",
            )


class TestBatchAllZeroGuard:
    """Tests for the issue #39 all-zero batch guard."""

    def test_all_zero_multi_point_raises(self):
        """Core bug from issue #39 — multiple all-zero points must raise."""
        pts = [{"time": i * 0.5, "value": 0.0} for i in range(8)]
        with pytest.raises(ReaperMCPError) as exc_info:
            _run_batch_guard(pts, "Volume")
        assert exc_info.value.error_code == ErrorCode.VALUE_OUT_OF_RANGE

    def test_single_zero_point_passes(self):
        """Single zero is a valid fade-to-silence point — must NOT raise."""
        pts = [{"time": 5.0, "value": 0.0}]
        _run_batch_guard(pts, "Volume")  # should not raise

    def test_mixed_batch_with_zeros_passes(self):
        """Not all-zero — should pass."""
        pts = [
            {"time": 0.0, "value": 1.0},
            {"time": 1.0, "value": 0.5},
            {"time": 2.0, "value": 0.0},
        ]
        _run_batch_guard(pts, "Volume")  # should not raise

    def test_two_zero_points_raises(self):
        """Minimum batch size for the guard is 2."""
        pts = [{"time": 0.0, "value": 0.0}, {"time": 1.0, "value": 0.0}]
        with pytest.raises(ReaperMCPError):
            _run_batch_guard(pts, "Volume")

    def test_pan_all_zero_passes(self):
        """Pan envelope — 0.0 is center pan, an all-zero Pan batch is valid."""
        pts = [{"time": i * 0.5, "value": 0.0} for i in range(4)]
        _run_batch_guard(pts, "Pan")  # should not raise

    def test_mute_all_zero_passes(self):
        """Mute envelope — all-zero means always unmuted, that is valid."""
        pts = [{"time": i * 1.0, "value": 0.0} for i in range(3)]
        _run_batch_guard(pts, "Mute")  # should not raise

    def test_fx_param_all_zero_passes(self):
        """FX param envelope — 0.0 is the parameter minimum, valid."""
        pts = [{"time": i * 0.5, "value": 0.0} for i in range(4)]
        _run_batch_guard(pts, "Volume", is_fx_param=True)  # should not raise

    def test_width_pre_fx_all_zero_raises(self):
        """Width (Pre-FX) is a gain envelope — all-zero batch must raise."""
        pts = [{"time": i * 0.5, "value": 0.0} for i in range(4)]
        with pytest.raises(ReaperMCPError):
            _run_batch_guard(pts, "Width (Pre-FX)")

    def test_non_zero_uniform_batch_passes(self):
        """A flat non-zero volume envelope (e.g. all 1.0) is perfectly fine."""
        pts = [{"time": i * 0.5, "value": 1.0} for i in range(10)]
        _run_batch_guard(pts, "Volume")  # should not raise

    def test_sine_shape_with_zeros_at_endpoints_passes(self):
        """A triangle/sine shape that touches 0.0 at start/end but not everywhere."""
        import math
        pts = [
            {"time": i * 0.1, "value": abs(math.sin(math.pi * i / 10))}
            for i in range(11)
        ]
        # Points 0 and 10 will be 0.0 (sin(0) = sin(pi) = 0), but not all
        _run_batch_guard(pts, "Volume")  # should not raise
