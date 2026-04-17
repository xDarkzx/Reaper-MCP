"""Plugin abstraction — translate human-readable EQ/reverb params to plugin-specific values.

Supports FabFilter Pro-Q 3 / Pro-R and REAPER stock ReaEQ / ReaVerbate.
"""

import math
import logging

from reaper_mcp.mix_engine.detect import PluginSuite

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
# ReaEQ frequency calibration (measured from plugin)
# ────────────────────────────────────────────────────────────────
_REAEQ_FREQ_POINTS = [
    (20.0,    0.0),
    (40.9,    0.05),
    (100.0,   0.141438),
    (158.9,   0.2),
    (300.0,   0.289506),
    (1000.0,  0.476049),
    (1160.5,  0.5),
    (5000.0,  0.739351),
    (24000.0, 1.0),
]

# ReaEQ gain: 0.25 = 0dB, linear 24dB/unit
_REAEQ_GAIN_CENTER = 0.25
_REAEQ_GAIN_SCALE = 24.0  # dB per unit


def _hz_to_reaeq(hz: float) -> float:
    """Convert Hz to ReaEQ normalized 0-1 via log-linear interpolation."""
    hz = max(20.0, min(24000.0, hz))
    log_hz = math.log(hz)
    for i in range(len(_REAEQ_FREQ_POINTS) - 1):
        f0, v0 = _REAEQ_FREQ_POINTS[i]
        f1, v1 = _REAEQ_FREQ_POINTS[i + 1]
        log_f0 = math.log(f0)
        log_f1 = math.log(f1)
        if log_hz <= log_f1:
            t = (log_hz - log_f0) / (log_f1 - log_f0)
            return v0 + t * (v1 - v0)
    return 1.0


def _db_to_reaeq_gain(db: float) -> float:
    """Convert dB to ReaEQ gain parameter (0-1). 0dB = 0.25."""
    return max(0.0, min(1.0, _REAEQ_GAIN_CENTER + db / _REAEQ_GAIN_SCALE))


# ────────────────────────────────────────────────────────────────
# FabFilter Pro-Q 3 calibration (measured from VST3 plugin)
# Frequency: freq = 10 * 3000^value  →  value = log(freq/10) / log(3000)
# Gain: 0.5 = 0dB, ±30dB range  →  value = 0.5 + gain_db / 60
# Q: Q = 0.025 * 1600^value  →  value = log(Q/0.025) / log(1600)
# ────────────────────────────────────────────────────────────────
_PROQ3_LOG_3000 = math.log(3000.0)
_PROQ3_LOG_1600 = math.log(1600.0)


def _hz_to_proq3(hz: float) -> float:
    """Convert Hz to Pro-Q 3 normalized 0-1. Exact formula: freq = 10 * 3000^value."""
    hz = max(10.0, min(30000.0, hz))
    return math.log(hz / 10.0) / _PROQ3_LOG_3000


def _db_to_proq3_gain(db: float) -> float:
    """Convert dB to Pro-Q 3 gain parameter (0-1). 0dB = 0.5, ±30dB range."""
    return max(0.0, min(1.0, 0.5 + db / 60.0))


def _q_to_proq3(q: float) -> float:
    """Convert Q factor to Pro-Q 3 normalized 0-1. Q=1.0 → 0.5."""
    q = max(0.025, min(40.0, q))
    return math.log(q / 0.025) / _PROQ3_LOG_1600


# ────────────────────────────────────────────────────────────────
# ReaVerbate helpers
# ────────────────────────────────────────────────────────────────
def _db_to_reaverbate_wet(db: float) -> float:
    """Convert dB to ReaVerbate wet param. 0dB=1.0, -6dB≈0.5, roughly linear in dB."""
    # ReaVerbate wet: 1.0 = 0dB, 0.5 ≈ -6dB → linear amplitude
    return max(0.0, min(1.0, 10 ** (db / 20.0)))


def _hz_to_reaverbate_lp(hz: float) -> float:
    """Convert Hz to ReaVerbate lowpass param. 20000Hz = 1.0."""
    return max(0.0, min(1.0, hz / 20000.0))


def _hz_to_reaverbate_hp(hz: float) -> float:
    """Convert Hz to ReaVerbate hipass param. ~20000Hz = 1.0, 0Hz = 0."""
    return max(0.0, min(1.0, hz / 20000.0))


# ────────────────────────────────────────────────────────────────
# Plugin profile classes
# ────────────────────────────────────────────────────────────────

class ReaperStockProfile:
    """Translates mix profiles to ReaEQ + ReaVerbate + ReaComp parameters."""

    name = "reaper_stock"
    eq_name = "ReaEQ"
    reverb_name = "ReaVerbate"
    compressor_name = "ReaComp"

    def eq_fx_chain_entry(self, eq_profile: dict) -> dict:
        """Build an fx_chain entry for ReaEQ from an EQ profile dict.

        ReaEQ has 4 default bands + we use band 5 as high-pass:
          Band 1 (Low Shelf):  idx 0,1,2  — freq, gain, bw
          Band 2 (Bell):       idx 3,4,5
          Band 3 (Bell):       idx 6,7,8
          Band 4 (High Shelf): idx 9,10,11
          Band 5 (High Pass):  idx 12,13,14
        """
        params = {}

        # High-pass filter on band 5
        hp_freq = eq_profile.get("hp_freq", 20)
        params[12] = _hz_to_reaeq(hp_freq)      # freq
        params[13] = _db_to_reaeq_gain(0.0)      # gain (0dB, HP uses slope not gain)
        params[14] = 0.7                          # steep Q for HP

        # Collect all EQ bands (cuts + boosts)
        all_bands = []
        for cut in eq_profile.get("cuts", []):
            all_bands.append(cut)
        for boost in eq_profile.get("boosts", []):
            all_bands.append(boost)

        # Map up to 4 bands to ReaEQ's 4 slots
        # Slot assignment: low_shelf → band1, high_shelf → band4, bells → band2/3
        low_shelf_band = None
        high_shelf_band = None
        bell_bands = []

        for band in all_bands:
            shape = band.get("shape", "bell")
            if shape == "low_shelf":
                low_shelf_band = band
            elif shape == "high_shelf":
                high_shelf_band = band
            else:
                bell_bands.append(band)

        # Band 1 — Low Shelf
        if low_shelf_band:
            params[0] = _hz_to_reaeq(low_shelf_band["freq"])
            params[1] = _db_to_reaeq_gain(low_shelf_band["gain_db"])
            params[2] = low_shelf_band.get("q", 0.8) / 5.0  # normalize Q
        else:
            # Disable band 1 (0 gain)
            params[1] = _db_to_reaeq_gain(0.0)

        # Band 2 — first bell
        if len(bell_bands) >= 1:
            b = bell_bands[0]
            params[3] = _hz_to_reaeq(b["freq"])
            params[4] = _db_to_reaeq_gain(b["gain_db"])
            params[5] = b.get("q", 1.0) / 5.0
        else:
            params[4] = _db_to_reaeq_gain(0.0)

        # Band 3 — second bell
        if len(bell_bands) >= 2:
            b = bell_bands[1]
            params[6] = _hz_to_reaeq(b["freq"])
            params[7] = _db_to_reaeq_gain(b["gain_db"])
            params[8] = b.get("q", 1.0) / 5.0
        else:
            params[7] = _db_to_reaeq_gain(0.0)

        # Band 4 — High Shelf
        if high_shelf_band:
            params[9] = _hz_to_reaeq(high_shelf_band["freq"])
            params[10] = _db_to_reaeq_gain(high_shelf_band["gain_db"])
            params[11] = high_shelf_band.get("q", 0.8) / 5.0
        else:
            params[10] = _db_to_reaeq_gain(0.0)

        return {
            "name": self.eq_name,
            "params_by_index": params,
        }

    def compression_fx_chain_entry(self, comp_profile: dict) -> dict:
        """Build an fx_chain entry for ReaComp from a compression profile dict.

        ReaComp param indices (measured from plugin):
          0: Thresh       — 0.0=-60dB, 1.0=0dB (linear in dB)
          1: Pre-Comp     — lookahead ms (0-1, we keep at 0)
          2: Attack       — 0.0=0.1ms, 1.0=1000ms (log scale)
          3: Release      — 0.0=1ms, 1.0=3000ms (log scale)
          4: Ratio         — 0.0=1:1, 1.0=20:1 (ish, nonlinear)
          5: Knee          — 0.0=0dB, 1.0=max knee
          6: RMS size      — detection window (default ~0.01)
          7: Makeup/Output — 0.0=-inf, 0.5=0dB, 1.0=+24dB
        """
        import math
        thresh = comp_profile.get("threshold_db", -18.0)
        ratio = comp_profile.get("ratio", 2.0)
        attack_ms = comp_profile.get("attack_ms", 20.0)
        release_ms = comp_profile.get("release_ms", 150.0)
        makeup_db = comp_profile.get("makeup_db", 2.0)
        knee_db = comp_profile.get("knee_db", 6.0)

        # Thresh: -60dB=0.0, 0dB=1.0
        thresh_norm = max(0.0, min(1.0, (thresh + 60.0) / 60.0))

        # Attack: log scale ~0.1ms to ~1000ms
        attack_norm = max(0.0, min(1.0, math.log10(max(0.1, attack_ms) / 0.1) / 4.0))

        # Release: log scale ~1ms to ~3000ms
        release_norm = max(0.0, min(1.0, math.log10(max(1.0, release_ms)) / math.log10(3000)))

        # Ratio: approximate — 1:1=0, 4:1≈0.25, 10:1≈0.5, 20:1=1.0
        ratio_norm = max(0.0, min(1.0, (ratio - 1.0) / 19.0))

        # Knee: 0dB=0.0, ~12dB=1.0
        knee_norm = max(0.0, min(1.0, knee_db / 12.0))

        # Makeup: 0dB=0.5, +24dB=1.0
        makeup_norm = max(0.0, min(1.0, 0.5 + makeup_db / 48.0))

        return {
            "name": self.compressor_name,
            "params_by_index": {
                0: thresh_norm,
                1: 0.0,            # pre-comp off
                2: attack_norm,
                3: release_norm,
                4: ratio_norm,
                5: knee_norm,
                6: 0.01,           # RMS size default
                7: makeup_norm,
            },
        }

    def reverb_fx_chain_entry(self, reverb_config: dict) -> dict:
        """Build an fx_chain entry for ReaVerbate from a reverb config dict."""
        return {
            "name": self.reverb_name,
            "params_by_index": {
                0: _db_to_reaverbate_wet(reverb_config.get("wet_db", -6.0)),
                # Dry OFF — this plugin sits on a return bus; the dry signal
                # reaches the bus via the send, so non-zero dry here would
                # double the level. Was previously 1.0 (bug), causing ~3dB
                # too-loud reverb returns.
                1: 0.0,
                2: reverb_config.get("room_size", 0.5),
                3: reverb_config.get("dampening", 0.5),
                4: reverb_config.get("width", 1.0),
                5: 0.0,  # delay = 0ms
                6: _hz_to_reaverbate_lp(reverb_config.get("lowpass_hz", 20000)),
                7: _hz_to_reaverbate_hp(reverb_config.get("hipass_hz", 0)),
            },
        }


class FabFilterProfile:
    """Translates mix profiles to FabFilter Pro-Q 3 + Pro-R + Pro-C 2 parameters.

    Pro-Q 3 VST3 band layout (13 params per band, starting at band_num * 13):
      +0: Used (1.0 = active)
      +1: Enabled (1.0 = on)
      +2: Frequency (10-30kHz exponential)
      +3: Gain (0.5 = 0dB, ±30dB)
      +4: Dynamic Range
      +5: Dynamics Enabled
      +6: Threshold
      +7: Q (0.5 = Q of 1.0, log scale 0.025-40)
      +8: Shape (Bell=0, LowShelf≈0.143, LowCut≈0.286, HighShelf≈0.429, HighCut≈0.571)
      +9: Slope
      +10: Stereo Placement
      +11: Speakers
      +12: Solo
    """

    name = "fabfilter"
    eq_name = "FabFilter Pro-Q 3"
    reverb_name = "FabFilter Pro-R"
    compressor_name = "FabFilter Pro-C 2"

    # Pro-Q 3 band shape values (normalized, 8 shapes mapped to 0/7..7/7)
    _SHAPE_BELL = 0.0
    _SHAPE_LOW_SHELF = 1.0 / 7.0    # ≈ 0.143
    _SHAPE_LOW_CUT = 2.0 / 7.0      # ≈ 0.286
    _SHAPE_HIGH_SHELF = 3.0 / 7.0   # ≈ 0.429
    _SHAPE_HIGH_CUT = 4.0 / 7.0     # ≈ 0.571

    def _band_params(self, band_num: int, freq_hz: float, gain_db: float,
                     q: float = 1.0, shape: float = 0.0) -> dict:
        """Generate params_by_index entries for one Pro-Q 3 band."""
        base = band_num * 13
        return {
            base + 0: 1.0,                    # Used = active
            base + 1: 1.0,                    # Enabled
            base + 2: _hz_to_proq3(freq_hz),  # Frequency
            base + 3: _db_to_proq3_gain(gain_db),  # Gain
            base + 7: _q_to_proq3(q),         # Q
            base + 8: shape,                  # Shape
        }

    def eq_fx_chain_entry(self, eq_profile: dict) -> dict:
        """Build an fx_chain entry for Pro-Q 3."""
        params = {}
        band_num = 0

        # High-pass filter
        hp_freq = eq_profile.get("hp_freq", 20)
        if hp_freq > 20:
            params.update(self._band_params(
                band_num, hp_freq, 0.0, q=0.7, shape=self._SHAPE_LOW_CUT
            ))
            band_num += 1

        # All EQ bands (cuts + boosts)
        for band in eq_profile.get("cuts", []) + eq_profile.get("boosts", []):
            shape_name = band.get("shape", "bell")
            if shape_name == "low_shelf":
                shape = self._SHAPE_LOW_SHELF
            elif shape_name == "high_shelf":
                shape = self._SHAPE_HIGH_SHELF
            else:
                shape = self._SHAPE_BELL

            params.update(self._band_params(
                band_num, band["freq"], band["gain_db"],
                q=band.get("q", 1.0), shape=shape,
            ))
            band_num += 1

        return {
            "name": self.eq_name,
            "params_by_index": params,
        }

    def compression_fx_chain_entry(self, comp_profile: dict) -> dict:
        """Build an fx_chain entry for FabFilter Pro-C 2.

        Uses fuzzy param name matching for version robustness.
        Pro-C 2 threshold: -60dB to 0dB → 0.0 to 1.0
        Pro-C 2 ratio: 1:1 to inf → 0.0 to 1.0
        Pro-C 2 attack/release: log scale via fuzzy names
        Pro-C 2 knee: 0-72dB → 0.0 to 1.0
        Pro-C 2 makeup/output: -24 to +24dB → 0.0 to 1.0
        """
        thresh = comp_profile.get("threshold_db", -18.0)
        ratio = comp_profile.get("ratio", 2.0)
        attack_ms = comp_profile.get("attack_ms", 20.0)
        release_ms = comp_profile.get("release_ms", 150.0)
        makeup_db = comp_profile.get("makeup_db", 2.0)
        knee_db = comp_profile.get("knee_db", 6.0)

        # Pro-C 2 uses 0.0=-60dB, 1.0=0dB for threshold
        thresh_norm = max(0.0, min(1.0, (thresh + 60.0) / 60.0))

        # Ratio: 1:1=0.0, ~20:1≈0.85, inf=1.0
        import math
        ratio_norm = max(0.0, min(1.0, math.log2(max(1.0, ratio)) / math.log2(20)))

        # Attack: ~0.005ms to 250ms, log scale
        attack_norm = max(0.0, min(1.0, math.log10(max(0.005, attack_ms) / 0.005) / math.log10(50000)))

        # Release: ~0.5ms to 2500ms, log scale
        release_norm = max(0.0, min(1.0, math.log10(max(0.5, release_ms) / 0.5) / math.log10(5000)))

        # Knee: 0-72dB
        knee_norm = max(0.0, min(1.0, knee_db / 72.0))

        # Makeup: -24 to +24dB → 0.0 to 1.0
        makeup_norm = max(0.0, min(1.0, 0.5 + makeup_db / 48.0))

        return {
            "name": self.compressor_name,
            "params": {
                "Threshold": thresh_norm,
                "Ratio": ratio_norm,
                "Attack": attack_norm,
                "Release": release_norm,
                "Knee": knee_norm,
                "Output Gain": makeup_norm,
            },
        }

    def reverb_fx_chain_entry(self, reverb_config: dict) -> dict:
        """Build an fx_chain entry for Pro-R.

        Uses fuzzy param name matching since Pro-R param indices vary by version.
        Pro-R's "Space" already encodes decay behaviour — we don't set a
        separate "Decay" because the previous (buggy) version fed room_size
        into Decay, which collapsed decay time to the default when room_size
        was small and is redundant when it's large.
        """
        return {
            "name": self.reverb_name,
            "params": {
                "Space": reverb_config.get("room_size", 0.5),
                "Brightness": 1.0 - reverb_config.get("dampening", 0.5),
            },
        }


def get_plugin_profile(suite: PluginSuite):
    """Return the appropriate plugin profile for the detected suite."""
    if suite == PluginSuite.FABFILTER:
        return FabFilterProfile()
    return ReaperStockProfile()
