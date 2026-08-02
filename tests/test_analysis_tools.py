"""Tests for reaper_mcp/tools/analysis_tools.py's edit-oriented QC detectors.

Pure numpy logic — synthetic arrays, no real audio files needed. Skipped
entirely if numpy isn't installed (matches this module's own optional
numpy/soundfile/pyloudnorm dependency).
"""

import pytest

np = pytest.importorskip("numpy")

from reaper_mcp.tools.analysis_tools import (
    _find_silence_candidates,
    _find_peak_candidates,
    _clamp_region,
    _truncate_candidates,
)


class TestFindSilenceCandidates:
    def test_no_silence_in_loud_signal(self):
        sr = 44100
        mono = np.full(sr, 0.5, dtype=np.float64)
        candidates = _find_silence_candidates(mono, sr, threshold_db=-40.0, min_duration=0.3)
        assert candidates == []

    def test_finds_injected_silence_span(self):
        sr = 44100
        mono = np.full(sr * 2, 0.5, dtype=np.float64)
        start_sample = sr * 1
        end_sample = start_sample + int(sr * 0.5)
        mono[start_sample:end_sample] = 0.0001
        candidates = _find_silence_candidates(mono, sr, threshold_db=-40.0, min_duration=0.3)
        assert len(candidates) == 1
        assert candidates[0]["start_sec"] == pytest.approx(1.0, abs=0.01)
        assert candidates[0]["duration_sec"] == pytest.approx(0.5, abs=0.01)

    def test_short_silence_below_min_duration_not_flagged(self):
        sr = 44100
        mono = np.full(sr, 0.5, dtype=np.float64)
        mono[1000:1000 + int(sr * 0.1)] = 0.0
        candidates = _find_silence_candidates(mono, sr, threshold_db=-40.0, min_duration=0.3)
        assert candidates == []

    def test_all_silent_file_flagged_as_one_span(self):
        sr = 44100
        mono = np.zeros(sr, dtype=np.float64)
        candidates = _find_silence_candidates(mono, sr, threshold_db=-40.0, min_duration=0.3)
        assert len(candidates) == 1
        assert candidates[0]["duration_sec"] == pytest.approx(1.0, abs=0.01)

    def test_empty_array_returns_no_candidates(self):
        candidates = _find_silence_candidates(np.array([]), 44100, threshold_db=-40.0, min_duration=0.3)
        assert candidates == []


class TestFindPeakCandidates:
    def test_no_candidates_in_silence(self):
        sr = 44100
        mono = np.zeros(sr, dtype=np.float64)
        candidates = _find_peak_candidates(mono, sr, sensitivity=3.0)
        assert candidates == []

    def test_no_candidates_in_steady_tone(self):
        sr = 44100
        t = np.arange(sr) / sr
        mono = 0.5 * np.sin(2 * np.pi * 440 * t)
        candidates = _find_peak_candidates(mono, sr, sensitivity=3.0)
        assert candidates == []

    def test_finds_injected_spike_against_quiet_baseline(self):
        sr = 44100
        rng = np.random.default_rng(42)
        mono = rng.normal(0, 1e-5, sr).astype(np.float64)
        spike_idx = sr // 2
        mono[spike_idx:spike_idx + 5] = 0.5
        candidates = _find_peak_candidates(mono, sr, sensitivity=3.0)
        assert len(candidates) == 1
        assert candidates[0]["time_sec"] == pytest.approx(spike_idx / sr, abs=0.001)
        assert candidates[0]["magnitude_db"] is not None
        assert candidates[0]["magnitude_db"] > -10.0

    def test_empty_array_returns_no_candidates(self):
        candidates = _find_peak_candidates(np.array([]), 44100, sensitivity=3.0)
        assert candidates == []

    def test_higher_sensitivity_finds_fewer_candidates(self):
        sr = 44100
        rng = np.random.default_rng(7)
        mono = rng.normal(0, 1e-4, sr).astype(np.float64)
        bump_idx = sr // 2
        mono[bump_idx:bump_idx + 5] = 0.01
        low_sensitivity = _find_peak_candidates(mono, sr, sensitivity=1.0)
        high_sensitivity = _find_peak_candidates(mono, sr, sensitivity=50.0)
        assert len(low_sensitivity) >= len(high_sensitivity)

    def test_busy_percussive_signal_can_produce_hundreds_of_candidates(self):
        """The scenario the truncation cap exists for: a busy mix (regular
        transients throughout, e.g. hi-hats) triggers one candidate per hit
        with nothing to cap the total — confirms the underlying detector is
        genuinely unbounded, not just theoretically so."""
        sr = 44100
        duration_sec = 30
        rng = np.random.default_rng(1)
        mono = rng.normal(0, 1e-5, sr * duration_sec).astype(np.float64)
        # A transient every 1/8 second — 8 hits/sec, 30s = 240 candidates.
        hit_every = int(sr * 0.125)
        for start in range(0, len(mono) - 5, hit_every):
            mono[start:start + 5] = 0.5
        candidates = _find_peak_candidates(mono, sr, sensitivity=3.0)
        assert len(candidates) > 200  # comfortably over MAX_ANALYSIS_CANDIDATES (300) territory


class TestTruncateCandidates:
    def test_under_cap_returns_unchanged_not_truncated(self):
        items = [{"i": i} for i in range(5)]
        result, truncated = _truncate_candidates(items, max_n=10)
        assert result == items
        assert truncated is False

    def test_exactly_at_cap_not_truncated(self):
        items = [{"i": i} for i in range(10)]
        result, truncated = _truncate_candidates(items, max_n=10)
        assert result == items
        assert truncated is False

    def test_over_cap_truncated_and_sliced(self):
        items = [{"i": i} for i in range(15)]
        result, truncated = _truncate_candidates(items, max_n=10)
        assert len(result) == 10
        assert truncated is True
        assert result == items[:10]  # keeps the first N, not a random subset

    def test_empty_list_not_truncated(self):
        result, truncated = _truncate_candidates([], max_n=10)
        assert result == []
        assert truncated is False


class TestClampRegion:
    def test_region_within_bounds_unchanged(self):
        assert _clamp_region(2.0, 5.0, 10.0) == (2.0, 5.0)

    def test_end_past_file_duration_clamped(self):
        assert _clamp_region(8.0, 15.0, 10.0) == (8.0, 10.0)

    def test_start_negative_clamped_to_zero(self):
        assert _clamp_region(-3.0, 5.0, 10.0) == (0.0, 5.0)

    def test_region_entirely_past_end_clamps_to_zero_length(self):
        assert _clamp_region(12.0, 15.0, 10.0) == (10.0, 10.0)

    def test_swapped_bounds_after_clamping_get_reordered(self):
        assert _clamp_region(6.0, 3.0, 10.0) == (3.0, 6.0)
