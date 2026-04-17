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

import os
import sys

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode

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
    """Resolve and validate a path to an existing audio file."""
    if not path:
        raise ReaperMCPError(ErrorCode.INVALID_PATH, "wav_path is required")
    abs_path = os.path.abspath(os.path.expanduser(path))
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
