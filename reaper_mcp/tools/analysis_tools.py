"""Audio analysis tools.

Reads a rendered WAV file from disk and returns objective mix metrics —
LUFS loudness, true-peak clipping, frequency balance, stereo-field health.

Designed to pair with `project_export_audio` and `engine_master`:

    1. engine_master("melodic_dubstep")
    2. project_export_audio("C:/renders/mix.wav")
    3. analyze_loudness("C:/renders/mix.wav")
    4. engine_fix_mix(...) if the numbers are off

Requires optional dependencies: numpy, soundfile, pyloudnorm.
Install with: pip install 'reaper-mcp[analysis]'
"""

import json
import os
import sys

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode
from reaper_mcp_shared.path_safety import safe_path
from reaper_mcp_shared.constants import (
    MAX_ANALYSIS_CANDIDATES, MAX_ANALYSIS_CANDIDATES_PER_REGION,
)

try:
    import numpy as np
    import soundfile as sf
    import pyloudnorm as pyln
    _AVAILABLE = True
    _IMPORT_ERROR = ""
except ImportError as e:
    _AVAILABLE = False
    _IMPORT_ERROR = str(e)


# LUFS targets for common release contexts (dB LUFS).
_LUFS_REFERENCE = {
    "streaming": -14.0,
    "spotify": -14.0,
    "apple_music": -16.0,
    "youtube": -14.0,
    "broadcast": -23.0,
    "cinema": -27.0,
    "club": -8.0,
}


def _safe_audio_path(path: str) -> str:
    """Resolve and validate a path to an existing audio file.

    Routes through the same system-directory/traversal guard every other
    path-accepting tool uses (project_open, item_insert_media, etc.) —
    previously this was the one path parameter in the codebase with no such
    check, low risk in practice (read-only, and soundfile.read() rejects
    anything that isn't actually a valid audio file) but inconsistent.
    """
    if not path:
        raise ReaperMCPError(ErrorCode.INVALID_PATH, "wav_path is required")
    abs_path = safe_path(path)
    if not os.path.isfile(abs_path):
        raise ReaperMCPError(
            ErrorCode.INVALID_PATH,
            f"File not found: {abs_path}. Render first with project_export_audio().",
        )
    return abs_path


def _load_wav(path: str):
    """Load an audio file. Returns (samples, sample_rate) where samples is
    shape (N,) for mono or (N, 2) for stereo."""
    abs_path = _safe_audio_path(path)
    try:
        samples, sr = sf.read(abs_path, always_2d=False)
    except Exception as e:
        raise ReaperMCPError(
            ErrorCode.COMMAND_FAILED,
            f"Failed to read audio file: {e}",
        )
    return samples, sr


def _to_mono(samples):
    if samples.ndim == 1:
        return samples
    return samples.mean(axis=1)


def _peak_db(samples) -> float:
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak <= 0.0:
        return -float("inf")
    return 20.0 * np.log10(peak)


def _find_silence_candidates(mono, sr: int, threshold_db: float, min_duration: float) -> list:
    if mono.size == 0:
        return []
    threshold_linear = 10 ** (threshold_db / 20.0)
    below = np.abs(mono) <= threshold_linear
    candidates = []
    n = len(below)
    i = 0
    while i < n:
        if below[i]:
            start = i
            while i < n and below[i]:
                i += 1
            end = i
            duration = (end - start) / sr
            if duration >= min_duration:
                candidates.append({
                    "start_sec": round(start / sr, 3),
                    "end_sec": round(end / sr, 3),
                    "duration_sec": round(duration, 3),
                })
        else:
            i += 1
    return candidates


def _find_peak_candidates(mono, sr: int, sensitivity: float) -> list:
    n = mono.size
    if n == 0:
        return []
    abs_samples = np.abs(mono)
    window = max(1, int(sr * 0.05))  # 50ms local baseline window
    kernel = np.ones(window) / window
    # Edge-pad (not zero-pad) before convolving — mode="same" implicitly
    # zero-pads outside the array, which drags the baseline artificially low
    # right at the start/end of the file and false-positives on ordinary
    # audio that starts or ends at full volume (the common case).
    left_pad = window // 2
    right_pad = window - 1 - left_pad
    padded = np.pad(abs_samples, (left_pad, right_pad), mode="edge")
    baseline = np.convolve(padded, kernel, mode="valid")
    # -60 dBFS: below this, content is near the noise floor of ordinary
    # background/room tone, which fluctuates around its own tiny baseline
    # and would otherwise trip a purely multiplicative threshold (an
    # earlier -80 dBFS floor let exactly this happen — verified live
    # against a synthetic near-silent span, which produced 17 false
    # "click" candidates from nothing but random noise variance).
    floor = 10 ** (-60.0 / 20.0)
    threshold = baseline * sensitivity + floor
    flagged = abs_samples > threshold
    # The first/last half-window still has no reliable local baseline no
    # matter the padding scheme — a periodic or ramping signal right at a
    # boundary has no stable "before" context. Exclude these edges from
    # detection entirely rather than guessing (standard practice for
    # windowed transient detectors).
    half_window = window // 2
    if half_window > 0:
        flagged[:half_window] = False
        if half_window < n:
            flagged[-half_window:] = False

    candidates = []
    i = 0
    while i < n:
        if flagged[i]:
            start = i
            while i < n and flagged[i]:
                i += 1
            end = i
            segment = abs_samples[start:end]
            peak_offset = int(np.argmax(segment))
            peak_idx = start + peak_offset
            magnitude = float(abs_samples[peak_idx])
            if magnitude > 0:
                magnitude_db = round(20.0 * np.log10(magnitude), 2)
            else:
                magnitude_db = None
            candidates.append({
                "time_sec": round(peak_idx / sr, 3),
                "magnitude_db": magnitude_db,
            })
        else:
            i += 1
    return candidates


def _truncate_candidates(candidates: list, max_n: int) -> tuple[list, bool]:
    """Cap a candidate list, reporting whether anything was cut.

    A busy percussive mix or a noisy dialogue take can produce far more
    candidates than anyone would review — same shape of problem as
    fx_set_preset's full-parameter dump, just triggered by content instead
    of a large plugin. Truncating without saying so would silently hide how
    many were found; `truncated=True` plus the true count lets the caller
    decide whether to narrow the analysis (e.g. a shorter region, a higher
    sensitivity) instead of drowning in candidates.
    """
    if len(candidates) <= max_n:
        return candidates, False
    return candidates[:max_n], True


def _clamp_region(start: float, end: float, total_duration_sec: float) -> tuple:
    start = max(0.0, min(start, total_duration_sec))
    end = max(0.0, min(end, total_duration_sec))
    if end < start:
        start, end = end, start
    return start, end


def register(mcp: FastMCP):
    if not _AVAILABLE:
        sys.stderr.write(
            f"\n[reaper-mcp] Audio analysis tools disabled — missing dependency: {_IMPORT_ERROR}\n"
            f"[reaper-mcp] Install with: pip install 'reaper-mcp[analysis]'\n\n"
        )
        return

    @mcp.tool()
    async def analyze_loudness(wav_path: str, reference: str = "streaming") -> dict:
        """Measure integrated loudness (LUFS), true peak, loudness range, and crest factor.

        Args:
            wav_path: Path to a rendered WAV file.
            reference: Reference target — streaming / spotify / apple_music / youtube /
                       broadcast / cinema / club. Default: streaming (-14 LUFS).

        Returns LUFS target deviation, headroom to 0 dBTP, and a qualitative hint.
        """
        samples, sr = _load_wav(wav_path)
        if samples.size == 0:
            raise ReaperMCPError(
                ErrorCode.COMMAND_FAILED,
                f"Audio file has no samples: {wav_path}. Render first and retry.",
            )
        samples_f = samples.astype(np.float64) if samples.dtype != np.float64 else samples

        meter = pyln.Meter(sr)
        integrated_lufs_raw = meter.integrated_loudness(samples_f)
        # pyloudnorm returns -inf for silent files. Report that honestly, don't
        # let the -inf leak into the JSON response (it's not valid JSON).
        if not np.isfinite(integrated_lufs_raw):
            return {
                "integrated_lufs": None,
                "true_peak_db": None,
                "rms_db": None,
                "crest_factor_db": None,
                "reference_target_lufs": _LUFS_REFERENCE.get(reference.lower(), -14.0),
                "reference": reference,
                "delta_lu": None,
                "hint": "Audio is silent — nothing to measure. Check the render.",
            }
        integrated_lufs = float(integrated_lufs_raw)

        mono = _to_mono(samples_f)
        peak_db = _peak_db(mono)
        rms = float(np.sqrt(np.mean(mono ** 2))) if mono.size else 0.0
        rms_db = 20.0 * np.log10(rms) if rms > 0 else -float("inf")
        crest_db = peak_db - rms_db if np.isfinite(peak_db) and np.isfinite(rms_db) else None

        target = _LUFS_REFERENCE.get(reference.lower(), -14.0)
        delta = integrated_lufs - target

        if abs(delta) < 0.5:
            hint = f"On target for {reference} (-{abs(target)} LUFS)."
        elif delta > 0:
            hint = f"Too loud by {delta:+.1f} LU — turn master down or limit harder for {reference}."
        else:
            hint = f"Too quiet by {delta:.1f} LU — raise master or add limiter gain for {reference}."

        return {
            "integrated_lufs": round(integrated_lufs, 2),
            "true_peak_db": round(peak_db, 2) if np.isfinite(peak_db) else None,
            "rms_db": round(rms_db, 2) if np.isfinite(rms_db) else None,
            "crest_factor_db": round(crest_db, 2) if crest_db is not None else None,
            "reference_target_lufs": target,
            "reference": reference,
            "delta_lu": round(delta, 2),
            "hint": hint,
        }

    @mcp.tool()
    async def analyze_clipping(wav_path: str, threshold_db: float = -0.1) -> dict:
        """Count samples at or above a clipping threshold (default -0.1 dBFS).

        Args:
            wav_path: Path to a rendered WAV file.
            threshold_db: Clip threshold in dBFS. -0.1 catches anything at/above -0.1 dBTP.

        Returns per-channel clipped-sample counts and percentage.
        """
        if threshold_db > 0:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                "threshold_db must be <= 0",
            )
        samples, sr = _load_wav(wav_path)
        threshold_linear = 10 ** (threshold_db / 20.0)

        if samples.ndim == 1:
            channels = [samples]
            channel_names = ["mono"]
        else:
            channels = [samples[:, i] for i in range(samples.shape[1])]
            channel_names = [f"ch_{i}" for i in range(samples.shape[1])]
            if samples.shape[1] == 2:
                channel_names = ["left", "right"]

        total_samples = samples.shape[0]
        per_channel = {}
        total_clipped = 0
        for name, ch in zip(channel_names, channels):
            clipped = int(np.sum(np.abs(ch) >= threshold_linear))
            pct = (clipped / total_samples * 100.0) if total_samples else 0.0
            per_channel[name] = {"clipped_samples": clipped, "percent": round(pct, 4)}
            total_clipped += clipped

        hint = (
            f"No clipping above {threshold_db} dBFS."
            if total_clipped == 0
            else f"{total_clipped} clipped samples — reduce master gain or tighten the limiter ceiling."
        )

        return {
            "threshold_db": threshold_db,
            "sample_rate": sr,
            "total_samples": total_samples,
            "per_channel": per_channel,
            "total_clipped_samples": total_clipped,
            "hint": hint,
        }

    @mcp.tool()
    async def analyze_silence(wav_path: str, threshold_db: float = -40.0, min_duration: float = 0.3) -> dict:
        """Find candidate silence spans — amplitude at/below threshold_db for at least min_duration.

        Flags candidates for review; does not claim certainty (e.g. an
        intentional dramatic pause looks identical to a bad edit here).

        Args:
            wav_path: Path to a rendered WAV file.
            threshold_db: Silence threshold in dBFS. Must be <= 0. Default -40.0.
            min_duration: Minimum span length in seconds to flag. Default 0.3.
        """
        if threshold_db > 0:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "threshold_db must be <= 0")
        if min_duration <= 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "min_duration must be > 0")
        samples, sr = _load_wav(wav_path)
        mono = _to_mono(samples.astype(np.float64))
        candidates = _find_silence_candidates(mono, sr, threshold_db, min_duration)
        total_found = len(candidates)
        total_silence = round(sum(c["duration_sec"] for c in candidates), 3)
        candidates, truncated = _truncate_candidates(candidates, MAX_ANALYSIS_CANDIDATES)
        hint = (
            "No silence candidates found."
            if not candidates
            else f"{len(candidates)} silence candidate(s) found ({total_silence}s total)."
        )
        if truncated:
            hint += (
                f" Truncated to {MAX_ANALYSIS_CANDIDATES} of {total_found} — "
                f"raise min_duration or split into smaller regions with analyze_region_qc."
            )
        return {
            "threshold_db": threshold_db,
            "min_duration": min_duration,
            "candidates": candidates,
            "candidates_found": total_found,
            "truncated": truncated,
            "total_silence_sec": total_silence,
            "hint": hint,
        }

    @mcp.tool()
    async def analyze_peaks(wav_path: str, sensitivity: float = 3.0) -> dict:
        """Find click/pop candidates — short transients that spike well above the local baseline.

        Distinct from analyze_clipping (which catches sustained over-threshold
        content): this looks for isolated spikes against the surrounding
        signal, the actual signature of a click/pop rather than a loud
        musical passage. The first/last ~25ms of the file are excluded from
        detection — there's no reliable local baseline right at a boundary.

        Args:
            wav_path: Path to a rendered WAV file.
            sensitivity: How many multiples of the local baseline counts as
                         a candidate. Higher = fewer, more confident candidates.
                         Must be > 0. Default 3.0.
        """
        if sensitivity <= 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "sensitivity must be > 0")
        samples, sr = _load_wav(wav_path)
        mono = _to_mono(samples.astype(np.float64))
        candidates = _find_peak_candidates(mono, sr, sensitivity)
        total_found = len(candidates)
        candidates, truncated = _truncate_candidates(candidates, MAX_ANALYSIS_CANDIDATES)
        hint = (
            "No peak/click candidates found."
            if not candidates
            else f"{len(candidates)} peak/click candidate(s) found — listen and trim "
                 f"or use spectral repair if confirmed."
        )
        if truncated:
            hint += (
                f" Truncated to {MAX_ANALYSIS_CANDIDATES} of {total_found} — "
                f"raise sensitivity to narrow down to the most confident hits."
            )
        return {
            "sensitivity": sensitivity,
            "candidates": candidates,
            "candidates_found": total_found,
            "truncated": truncated,
            "hint": hint,
        }

    @mcp.tool()
    async def analyze_region_qc(wav_path: str, regions: str) -> dict:
        """Per-region silence + peak/click candidate report — the post-production QC pass.

        regions is a JSON array populated from marker_get_all() (regions are
        markers with is_region: true), e.g.
        '[{"name":"Line 12","start":10.2,"end":14.8}]'. A region extending
        past the actual audio's duration is clamped, not rejected — the
        returned region's start/end reflect what was actually analyzed.

        Args:
            wav_path: Path to a rendered WAV file.
            regions: JSON array of {"name": str, "start": float, "end": float}.
        """
        try:
            parsed = json.loads(regions)
        except (json.JSONDecodeError, TypeError):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "Invalid regions JSON")
        if not isinstance(parsed, list) or len(parsed) == 0:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "regions must be a non-empty JSON array")
        if len(parsed) > 200:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, f"Too many regions: {len(parsed)} (max 200)")
        for i, r in enumerate(parsed):
            if "start" not in r or "end" not in r:
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, f"Region {i} missing start/end")

        samples, sr = _load_wav(wav_path)
        mono = _to_mono(samples.astype(np.float64))
        total_duration = mono.size / sr if sr else 0.0

        results = []
        total_flags = 0
        for r in parsed:
            start, end = _clamp_region(float(r["start"]), float(r["end"]), total_duration)
            start_idx = int(start * sr)
            end_idx = int(end * sr)
            segment = mono[start_idx:end_idx]

            silence = _find_silence_candidates(segment, sr, threshold_db=-40.0, min_duration=0.3)
            peaks = _find_peak_candidates(segment, sr, sensitivity=3.0)
            for c in silence:
                c["start_sec"] = round(c["start_sec"] + start, 3)
                c["end_sec"] = round(c["end_sec"] + start, 3)
            for c in peaks:
                c["time_sec"] = round(c["time_sec"] + start, 3)

            # Per-region cap, not just a whole-file one — up to 200 regions
            # in a single call means an unbounded per-region list multiplies
            # fast. Smaller than the whole-file cap since a QC pass over one
            # region is meant to be a quick read, not a full inventory.
            flag_count_found = len(silence) + len(peaks)
            silence, silence_truncated = _truncate_candidates(silence, MAX_ANALYSIS_CANDIDATES_PER_REGION)
            peaks, peaks_truncated = _truncate_candidates(peaks, MAX_ANALYSIS_CANDIDATES_PER_REGION)
            total_flags += flag_count_found
            results.append({
                "name": r.get("name", ""),
                "start": start,
                "end": end,
                "silence_candidates": silence,
                "peak_candidates": peaks,
                "flag_count": flag_count_found,
                "truncated": silence_truncated or peaks_truncated,
            })

        any_truncated = any(r["truncated"] for r in results)
        hint = (
            f"{total_flags} candidate(s) across {len(results)} region(s) — "
            f"review flagged regions before final edit."
            if total_flags
            else f"No candidates found across {len(results)} region(s)."
        )
        if any_truncated:
            hint += (
                f" One or more regions hit the {MAX_ANALYSIS_CANDIDATES_PER_REGION}-candidate "
                f"cap — check each region's own \"truncated\" flag."
            )
        return {
            "region_count": len(results),
            "regions": results,
            "total_flags": total_flags,
            "any_region_truncated": any_truncated,
            "hint": hint,
        }

    @mcp.tool()
    async def analyze_frequency_spectrum(wav_path: str) -> dict:
        """Bass / mid / treble energy split and spectral centroid.

        Args:
            wav_path: Path to a rendered WAV file.

        Returns per-band energy in dB, spectral centroid (perceived brightness),
        and a balance hint.
        """
        samples, sr = _load_wav(wav_path)
        mono = _to_mono(samples.astype(np.float64))
        if mono.size == 0:
            raise ReaperMCPError(ErrorCode.COMMAND_FAILED, "Empty audio file.")

        # FFT on full file — fine for ≤ 10-minute tracks at 48 kHz.
        fft = np.fft.rfft(mono)
        freqs = np.fft.rfftfreq(mono.size, 1.0 / sr)
        magnitudes = np.abs(fft)

        mag_sum = float(np.sum(magnitudes))
        if mag_sum <= 0.0:
            # Silence / DC-only signal — nothing useful to report.
            return {
                "sample_rate": sr,
                "band_energy_db": {},
                "spectral_centroid_hz": None,
                "hint": "Signal has no spectral content (silence or DC). Check the render.",
            }

        bands = {
            "sub": (20, 60),
            "bass": (60, 250),
            "low_mid": (250, 500),
            "mid": (500, 2000),
            "high_mid": (2000, 4000),
            "presence": (4000, 6000),
            "brilliance": (6000, 20000),
        }
        band_energy = {}
        for name, (lo, hi) in bands.items():
            mask = (freqs >= lo) & (freqs < hi)
            energy = float(np.sum(magnitudes[mask] ** 2))
            band_energy[name] = energy

        # Normalise against total energy for relative dB.
        total_energy = sum(band_energy.values()) or 1.0
        band_db = {k: round(10.0 * np.log10(v / total_energy), 2) if v > 0 else None
                   for k, v in band_energy.items()}

        # Spectral centroid — rough proxy for perceived brightness.
        # mag_sum already > 0 here (guard above), so this is safe.
        centroid = float(np.sum(freqs * magnitudes) / mag_sum)

        # Qualitative balance hint — guard against None entries from silent bands.
        def _bd(k): return band_db.get(k) or 0.0
        low_energy = _bd("sub") + _bd("bass")
        high_energy = _bd("presence") + _bd("brilliance")
        if low_energy - high_energy > 6:
            hint = "Low-heavy — consider a high-shelf boost or bass cut."
        elif high_energy - low_energy > 6:
            hint = "Top-heavy — consider a low-shelf boost or high-mid cut."
        else:
            hint = "Tonal balance within typical range."

        return {
            "sample_rate": sr,
            "band_energy_db": band_db,
            "spectral_centroid_hz": round(centroid, 1),
            "hint": hint,
        }

    @mcp.tool()
    async def analyze_stereo_field(wav_path: str) -> dict:
        """Stereo correlation, mid/side balance, and width estimate.

        Args:
            wav_path: Path to a rendered WAV file.

        Returns phase correlation (-1..+1), mid/side RMS ratio, width, and a hint
        about mono compatibility.
        """
        samples, sr = _load_wav(wav_path)
        if samples.ndim == 1 or samples.shape[1] == 1:
            return {
                "is_stereo": False,
                "hint": "Source is mono — stereo analysis not applicable.",
            }
        if samples.shape[1] != 2:
            raise ReaperMCPError(
                ErrorCode.COMMAND_FAILED,
                f"Expected mono or stereo, got {samples.shape[1]} channels.",
            )

        left = samples[:, 0].astype(np.float64)
        right = samples[:, 1].astype(np.float64)

        if left.size == 0:
            raise ReaperMCPError(ErrorCode.COMMAND_FAILED, "Empty audio file.")

        # Phase correlation via Pearson across the full signal. Guard against
        # one-or-both channels being constant (denom = 0 → NaN), which would
        # break JSON serialisation.
        l_centered = left - left.mean()
        r_centered = right - right.mean()
        denom = float(np.sqrt(np.sum(l_centered ** 2) * np.sum(r_centered ** 2)))
        if denom <= 0.0:
            # One or both channels are constant (e.g., all zeros / DC).
            return {
                "is_stereo": True,
                "sample_rate": sr,
                "phase_correlation": None,
                "mid_rms": 0.0,
                "side_rms": 0.0,
                "side_to_mid_ratio": None,
                "hint": "One or both channels are silent/constant — correlation undefined.",
            }
        correlation = float(np.sum(l_centered * r_centered) / denom)

        # Mid / side split.
        mid = (left + right) * 0.5
        side = (left - right) * 0.5
        mid_rms = float(np.sqrt(np.mean(mid ** 2))) if mid.size else 0.0
        side_rms = float(np.sqrt(np.mean(side ** 2))) if side.size else 0.0
        ratio = (side_rms / mid_rms) if mid_rms > 0 else 0.0

        if correlation < 0.2:
            hint = (
                f"Low correlation ({correlation:.2f}) — risk of phase cancellation in mono. "
                f"Check the low end is centered."
            )
        elif correlation > 0.95:
            hint = f"Very high correlation ({correlation:.2f}) — mix sounds almost mono. Widen pads / stereo effects."
        else:
            hint = f"Healthy stereo correlation ({correlation:.2f})."

        return {
            "is_stereo": True,
            "sample_rate": sr,
            "phase_correlation": round(correlation, 3),
            "mid_rms": round(mid_rms, 5),
            "side_rms": round(side_rms, 5),
            "side_to_mid_ratio": round(ratio, 3),
            "hint": hint,
        }
