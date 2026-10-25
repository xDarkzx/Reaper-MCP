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

# ReaEQ gain: measured live (fx_get_params read-back against REAPER 7.82 and
# independently against another install) — 0.25 = 0dB, and the scale is
# exponential (amplitude), not linear in dB. 0.1667 -> -3.5dB, 0.3333 -> +2.5dB,
# confirmed live both from a bug report's 12-point sweep and a fresh read-back
# in this session. The previous linear formula (0.25 + db/24) was wrong by a
# growing margin away from 0dB — e.g. an intended -2dB cut actually landed at
# -3.5dB.
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
    """Convert dB to ReaEQ gain parameter (0-1). 0.25 = 0dB, 1.0 = +12dB."""
    return max(0.0, min(1.0, 10 ** (db / 20.0) / 4.0))


def _q_to_reaeq_bw(q: float) -> float:
    """Convert Q factor to ReaEQ's BW parameter (0-1 = 0-4 octaves).

    Measured live: BW param value * 4 = bandwidth in octaves (0.2 -> 0.80oct,
    0.5 -> 2.00oct, confirmed via fx_get_params read-back). The previous
    code wrote q / 5.0 directly as the BW param — since BW increases with
    the param value, a higher Q (meant to be narrower) produced a *wider*
    band, backwards from what Q means. This uses the standard Q<->bandwidth
    relationship: octaves = 2/ln(2) * asinh(1 / (2*Q)).
    """
    q = max(0.01, q)
    octaves = 2.0 / math.log(2.0) * math.asinh(1.0 / (2.0 * q))
    return max(0.0, min(1.0, octaves / 4.0))


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


# ReaEQ band types (BANDTYPEx named config), read back live from REAPER 7.x.
_REAEQ_TYPE_LOW_SHELF = "0"
_REAEQ_TYPE_HIGH_SHELF = "1"
_REAEQ_TYPE_HP = "4"
_REAEQ_TYPE_BAND = "8"


def _reaeq_hp_enable(enabled: bool) -> dict:
    """named_config for ReaEQ band 5 (0-based "4"), the high-pass band.

    Measured on REAPER 7.82: band 5 exists but is disabled on new ReaEQ
    instances, so its frequency params alone have no audible effect.
    """
    return {"BANDENABLED4": "1" if enabled else "0"}


# ────────────────────────────────────────────────────────────────
# ReaVerbate helpers
# ────────────────────────────────────────────────────────────────
def _width_to_reaverbate(width: float) -> float:
    """ReaVerbate Width is -1.00..+1.00 across 0..1 (measured: 0.5 = 0.00,
    i.e. mono), so a 0..1 width needs (w + 1) / 2, not a pass-through."""
    return max(0.0, min(1.0, (width + 1.0) / 2.0))


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
    limiter_name = "ReaLimit"

    def eq_fx_chain_entry(self, eq_profile: dict) -> dict:
        """Build an fx_chain entry for ReaEQ from an EQ profile dict.

        ReaEQ's 5 default bands, 3 params each (freq, gain, bw):
          Band 1: idx 0,1,2    (default Low Shelf)
          Band 2: idx 3,4,5    (default Bell)
          Band 3: idx 6,7,8    (default Bell)
          Band 4: idx 9,10,11  (default High Shelf)
          Band 5: idx 12,13,14 (default High Pass, disabled)

        Band type and enable state aren't automatable params, so they go via
        named_config (BANDTYPEx / BANDENABLEDx). Type codes measured live:
        0 = Low Shelf, 1 = High Shelf, 4 = High Pass, 8 = Band (bell).
        Bands 1/4 switch to bells when no shelf needs them, so up to 4 bells
        fit. Band 5 is enabled only for a real high-pass.
        """
        params = {}

        # High-pass filter on band 5
        hp_freq = eq_profile.get("hp_freq", 20)
        params[12] = _hz_to_reaeq(hp_freq)      # freq
        params[13] = _db_to_reaeq_gain(0.0)      # gain (0dB, HP uses slope not gain)
        params[14] = 0.7                          # steep Q for HP
        named_config = _reaeq_hp_enable(hp_freq > 20)
        named_config["BANDTYPE4"] = _REAEQ_TYPE_HP

        # Collect all EQ bands (cuts + boosts)
        all_bands = []
        for cut in eq_profile.get("cuts", []):
            all_bands.append(cut)
        for boost in eq_profile.get("boosts", []):
            all_bands.append(boost)

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

        def write_band(slot, band, band_type, default_q):
            base = slot * 3
            params[base] = _hz_to_reaeq(band["freq"])
            params[base + 1] = _db_to_reaeq_gain(band["gain_db"])
            params[base + 2] = _q_to_reaeq_bw(band.get("q", default_q))
            named_config[f"BANDTYPE{slot}"] = band_type
            named_config[f"BANDENABLED{slot}"] = "1"

        bell_slots = [1, 2]
        if low_shelf_band:
            write_band(0, low_shelf_band, _REAEQ_TYPE_LOW_SHELF, 0.8)
        else:
            bell_slots.insert(0, 0)
        if high_shelf_band:
            write_band(3, high_shelf_band, _REAEQ_TYPE_HIGH_SHELF, 0.8)
        else:
            bell_slots.append(3)

        bell_bands.sort(key=lambda b: b["freq"])
        for slot, band in zip(bell_slots, bell_bands):
            write_band(slot, band, _REAEQ_TYPE_BAND, 1.0)
        for slot in bell_slots[len(bell_bands):]:
            params[slot * 3 + 1] = _db_to_reaeq_gain(0.0)  # unused slot: 0dB

        if len(bell_bands) > len(bell_slots):
            dropped = bell_bands[len(bell_slots):]
            logger.warning(
                "ReaEQ has %d bell slot(s) left after shelves; dropping %d band(s): %s",
                len(bell_slots), len(dropped),
                ", ".join(f"{b['freq']}Hz {b['gain_db']:+.1f}dB" for b in dropped),
            )

        return {
            "name": self.eq_name,
            "params_by_index": params,
            "named_config": named_config,
        }

    def compression_fx_chain_entry(self, comp_profile: dict) -> dict:
        """Build an fx_chain entry for ReaComp from a compression profile dict.

        ReaComp param indices — confirmed live via fx_get_params read-back
        (name + REAPER-formatted display), not assumed:
          0: Threshold    — amplitude, 10**(dB/20). 0.8333 reads "-0.00 dB".
          1: Ratio        — (ratio-1)/99. 0.0303 reads "4.00 :1".
          2: Attack       — linear ms/500. 0.006 reads "3.0 ms".
          3: Release      — linear ms/5000. 0.02 reads "100 ms".
          4: Pre-comp     — lookahead ms/250; kept at 0 (off).
          5: resvd        — unused; never written.
          6: Lowpass      — detector sidechain lowpass; 1.0 reads "20000 Hz"
                            (off/wide open). Kept at 1.0 so the detector
                            isn't filtered.
          7: Hipass       — detector sidechain highpass; 0.0 reads "0 Hz"
                            (off). Kept at 0.0 for the same reason.
          11: Wet         — amplitude, 10**(dB/20), confirmed live by setting
                            0.7/1.3 and reading back "-3.1 dB"/"+2.3 dB".
                            Used as makeup/output gain.
          13: RMS size    — detection window, kept at plugin default.
          14: Knee        — dB/24. 0.0 reads "0.0 dB".

        Previously this assumed Pre-comp was at 1 and Ratio at 4 (swapped),
        Knee at 5 (actually the unused "resvd" slot) and RMS size at 6
        (actually the detector's sidechain lowpass) — so ratio silently
        stayed at 1:1 always, knee was never set, and the detector's own
        sidechain was filtered through a 200Hz lowpass + ~11kHz highpass,
        leaving it nearly deaf. Makeup previously wrote to index 7
        ("Hipass"), which doesn't do anything useful as gain.
        """
        thresh = comp_profile.get("threshold_db", -18.0)
        ratio = comp_profile.get("ratio", 2.0)
        attack_ms = comp_profile.get("attack_ms", 20.0)
        release_ms = comp_profile.get("release_ms", 150.0)
        makeup_db = comp_profile.get("makeup_db", 2.0)
        knee_db = comp_profile.get("knee_db", 6.0)

        thresh_norm = max(0.0, min(1.0, 10 ** (thresh / 20.0)))
        ratio_norm = max(0.0, min(1.0, (ratio - 1.0) / 99.0))
        attack_norm = max(0.0, min(1.0, attack_ms / 500.0))
        release_norm = max(0.0, min(1.0, release_ms / 5000.0))
        knee_norm = max(0.0, min(1.0, knee_db / 24.0))
        makeup_norm = max(0.0, min(4.0, 10 ** (makeup_db / 20.0)))

        return {
            "name": self.compressor_name,
            "params_by_index": {
                0: thresh_norm,
                1: ratio_norm,
                2: attack_norm,
                3: release_norm,
                4: 0.0,            # pre-comp off
                6: 1.0,            # detector sidechain lowpass off
                7: 0.0,            # detector sidechain highpass off
                11: makeup_norm,   # Wet, used as makeup/output gain
                14: knee_norm,
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
                # Room size and dampening are linear across the param
                # (9-point fx_scan_params sweep: room size reads 30..98,
                # dampening 0..100), so 0..1 passes straight through.
                2: reverb_config.get("room_size", 0.5),
                3: reverb_config.get("dampening", 0.5),
                4: _width_to_reaverbate(reverb_config.get("width", 1.0)),
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
    limiter_name = "FabFilter Pro-L 2"

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
    """Return the plugin profile for one plugin family."""
    if suite == PluginSuite.FABFILTER:
        return FabFilterProfile()
    return ReaperStockProfile()


class CompositeProfile:
    """Builds each category's FX entry from that category's own plugin family,
    so a preference for one category (say ReaEQ for EQ) doesn't drag the others
    along. `selection.family(category)` says which family a category uses."""

    name = "composite"

    def __init__(self, selection):
        self._selection = selection

    def _for(self, category: str):
        return get_plugin_profile(self._selection.family(category))

    def eq_fx_chain_entry(self, eq_profile: dict) -> dict:
        return self._for("eq").eq_fx_chain_entry(eq_profile)

    def compression_fx_chain_entry(self, comp_profile: dict) -> dict:
        return self._for("compressor").compression_fx_chain_entry(comp_profile)

    def reverb_fx_chain_entry(self, reverb_config: dict) -> dict:
        return self._for("reverb").reverb_fx_chain_entry(reverb_config)


def get_plugin_profile_for(selection) -> CompositeProfile:
    """Return the profile for a per-category `PluginSelection`."""
    return CompositeProfile(selection)
