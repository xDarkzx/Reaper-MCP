"""Master-bus mastering pipeline.

Chain order (industry standard):
  1. Subtractive HP EQ (20-30 Hz, removes subsonic rumble)
  2. Bus glue compressor (1.5-2:1, slow attack, ~1-2dB GR)
  3. Tonal shelf EQ (low shelf for weight, high shelf for air)
  4. Stereo width (M/S processing, wider for EDM, narrower for rock)
  5. Brick-wall limiter (output ceiling at true_peak_db, push toward target LUFS)

Plugin auto-detection:
  - FabFilter Pro-Q 3 / Pro-C 2 / Pro-L 2 if available
  - REAPER stock (ReaEQ / ReaComp / ReaLimit / JS: Stereo Enhancer) otherwise

LUFS targeting: without a metering pass we cannot automatically dial input
gain. We set the limiter ceiling correctly; user pushes input gain to reach
target LUFS by ear or meter.
"""

import json
import logging

from reaper_mcp.mix_engine.detect import detect_plugins, PluginSuite
from reaper_mcp.mix_engine.profiles_v2 import (
    MasteringChain, EQBand, CompProfile, get_profile,
)

logger = logging.getLogger(__name__)


async def run_master_pipeline(client, style: str, clean: bool = True) -> dict:
    """Apply a complete mastering chain to the master bus for the given style."""
    profile = get_profile(style)
    if profile is None:
        return {"success": False, "error": f"Unknown style '{style}'"}

    suite = await detect_plugins(client)
    spec = profile.mastering

    fx_chain = _build_master_fx_chain(spec, suite)

    result = await client.execute(
        "setup_master_chain",
        fx_chain=json.dumps(fx_chain),
        clean=clean,
    )

    return {
        "success": True,
        "style": style,
        "target_lufs": spec.target_lufs,
        "true_peak_db": spec.true_peak_db,
        "stereo_width": spec.stereo_width,
        "limiter_character": spec.limiter_character,
        "plugin_suite": suite.value,
        "applied": result.get("data", result).get("fx_added", []),
        "cleared": result.get("data", result).get("cleared", 0),
    }


def _build_master_fx_chain(spec: MasteringChain, suite: PluginSuite) -> list[dict]:
    """Build the ordered FX chain for the master bus."""
    is_ff = (suite == PluginSuite.FABFILTER)
    chain: list[dict] = []

    # ─── 1. Subtractive EQ: HP + any bus_cuts ───────────────────
    if is_ff:
        chain.append(_ff_subtractive_eq(spec))
    else:
        chain.append(_rea_subtractive_eq(spec))

    # ─── 2. Bus glue compressor ─────────────────────────────────
    if spec.bus_comp is not None:
        if is_ff:
            chain.append(_ff_bus_comp(spec.bus_comp))
        else:
            chain.append(_rea_bus_comp(spec.bus_comp))

    # ─── 3. Tonal shelf EQ ──────────────────────────────────────
    if spec.low_shelf_db != 0.0 or spec.high_shelf_db != 0.0:
        if is_ff:
            chain.append(_ff_tonal_eq(spec))
        else:
            chain.append(_rea_tonal_eq(spec))

    # ─── 4. Stereo width (only if not 1.0) ──────────────────────
    if abs(spec.stereo_width - 1.0) > 0.01:
        chain.append(_stereo_width_fx(spec.stereo_width))

    # ─── 5. Limiter ─────────────────────────────────────────────
    if is_ff:
        chain.append(_ff_limiter(spec))
    else:
        chain.append(_rea_limiter(spec))

    return chain


# ────────────────────────── ReaEQ builders ──────────────────────────

def _rea_subtractive_eq(spec: MasteringChain) -> dict:
    """ReaEQ: HP at 25Hz to strip subsonic rumble + optional bus cuts."""
    import math

    # ReaEQ freq normalization (log-linear)
    def hz_to_reaeq(hz):
        hz = max(20.0, min(24000.0, hz))
        # Approximate log-linear: 20Hz=0, 24kHz=1
        return math.log(hz / 20.0) / math.log(24000.0 / 20.0)

    def db_to_reaeq(db):
        return max(0.0, min(1.0, 0.25 + db / 24.0))

    params = {
        # Band 5 = high-pass
        12: hz_to_reaeq(25),        # HP at 25Hz for subsonic
        13: db_to_reaeq(0.0),
        14: 0.7,
        # Silence other bands
        1: db_to_reaeq(0.0),
        4: db_to_reaeq(0.0),
        7: db_to_reaeq(0.0),
        10: db_to_reaeq(0.0),
    }
    return {"name": "ReaEQ", "params_by_index": params}


def _rea_tonal_eq(spec: MasteringChain) -> dict:
    import math
    def hz_to_reaeq(hz):
        hz = max(20.0, min(24000.0, hz))
        return math.log(hz / 20.0) / math.log(24000.0 / 20.0)
    def db_to_reaeq(db):
        return max(0.0, min(1.0, 0.25 + db / 24.0))

    params = {
        # Band 1 = Low shelf
        0: hz_to_reaeq(spec.low_shelf_freq),
        1: db_to_reaeq(spec.low_shelf_db),
        2: 0.8 / 5.0,
        # Band 4 = High shelf
        9: hz_to_reaeq(spec.high_shelf_freq),
        10: db_to_reaeq(spec.high_shelf_db),
        11: 0.7 / 5.0,
        # Silence band 2/3 and HP
        4: db_to_reaeq(0.0),
        7: db_to_reaeq(0.0),
        13: db_to_reaeq(0.0),
    }
    return {"name": "ReaEQ", "params_by_index": params}


def _rea_bus_comp(comp: CompProfile) -> dict:
    """ReaComp — gentle master bus glue."""
    import math

    def norm_thresh(db):
        return max(0.0, min(1.0, (db + 60.0) / 60.0))
    def norm_ratio(r):
        return max(0.0, min(1.0, (r - 1.0) / 19.0))
    def norm_attack(ms):
        return max(0.0, min(1.0, math.log10(max(0.1, ms) / 0.1) / 4.0))
    def norm_release(ms):
        return max(0.0, min(1.0, math.log10(max(1.0, ms)) / math.log10(3000)))
    def norm_makeup(db):
        return max(0.0, min(1.0, 0.5 + db / 48.0))

    return {
        "name": "ReaComp",
        "params_by_index": {
            0: norm_thresh(comp.threshold_db),
            1: 0.0,
            2: norm_attack(comp.attack_ms),
            3: norm_release(comp.release_ms),
            4: norm_ratio(comp.ratio),
            5: max(0.0, min(1.0, comp.knee_db / 12.0)),
            6: 0.01,
            7: norm_makeup(comp.makeup_db),
        },
    }


def _rea_limiter(spec: MasteringChain) -> dict:
    """ReaLimit / JS: Limiter — set ceiling at true_peak_db."""
    # ReaLimit params: 0=Threshold (aka input gain), 1=Ceiling, 2=Release
    # Threshold 0=-60dB .. 1=0dB; start at 0dB (no drive), user tunes up
    # Ceiling 0=-60dB .. 1=0dB
    def norm_db(db):
        return max(0.0, min(1.0, (db + 60.0) / 60.0))

    release_norm = {"transparent": 0.5, "warm": 0.7, "punchy": 0.3, "aggressive": 0.2}
    return {
        "name": "ReaLimit",
        "params_by_index": {
            0: norm_db(0.0),                       # threshold (input) — user tweaks
            1: norm_db(spec.true_peak_db),         # ceiling
            2: release_norm.get(spec.limiter_character, 0.4),
        },
    }


# ─────────────────────── FabFilter builders ───────────────────────

def _ff_subtractive_eq(spec: MasteringChain) -> dict:
    """Pro-Q 3: HP at 25Hz (low cut)."""
    import math
    LOG_3000 = math.log(3000.0)
    def hz_to_proq3(hz):
        hz = max(10.0, min(30000.0, hz))
        return math.log(hz / 10.0) / LOG_3000

    # Band 0 = low cut at 25Hz
    base = 0
    params = {
        base + 0: 1.0,                       # Used
        base + 1: 1.0,                       # Enabled
        base + 2: hz_to_proq3(25),
        base + 3: 0.5,                       # 0dB (cut not shelf)
        base + 7: 0.5,                       # Q=1
        base + 8: 2.0 / 7.0,                 # Low cut shape
    }
    return {"name": "FabFilter Pro-Q 3", "params_by_index": params}


def _ff_tonal_eq(spec: MasteringChain) -> dict:
    import math
    LOG_3000 = math.log(3000.0)
    def hz_to_proq3(hz):
        hz = max(10.0, min(30000.0, hz))
        return math.log(hz / 10.0) / LOG_3000
    def db_to_proq3(db):
        return max(0.0, min(1.0, 0.5 + db / 60.0))

    params = {}
    # Band 0 = low shelf
    if spec.low_shelf_db != 0.0:
        base = 0
        params.update({
            base + 0: 1.0, base + 1: 1.0,
            base + 2: hz_to_proq3(spec.low_shelf_freq),
            base + 3: db_to_proq3(spec.low_shelf_db),
            base + 7: 0.5,
            base + 8: 1.0 / 7.0,
        })
    # Band 1 = high shelf
    if spec.high_shelf_db != 0.0:
        base = 13
        params.update({
            base + 0: 1.0, base + 1: 1.0,
            base + 2: hz_to_proq3(spec.high_shelf_freq),
            base + 3: db_to_proq3(spec.high_shelf_db),
            base + 7: 0.5,
            base + 8: 3.0 / 7.0,
        })
    return {"name": "FabFilter Pro-Q 3", "params_by_index": params}


def _ff_bus_comp(comp: CompProfile) -> dict:
    import math
    def norm_thresh(db):
        return max(0.0, min(1.0, (db + 60.0) / 60.0))
    def norm_ratio(r):
        return max(0.0, min(1.0, math.log2(max(1.0, r)) / math.log2(20)))
    def norm_attack(ms):
        return max(0.0, min(1.0, math.log10(max(0.005, ms) / 0.005) / math.log10(50000)))
    def norm_release(ms):
        return max(0.0, min(1.0, math.log10(max(0.5, ms) / 0.5) / math.log10(5000)))

    return {
        "name": "FabFilter Pro-C 2",
        "params": {
            "Threshold": norm_thresh(comp.threshold_db),
            "Ratio": norm_ratio(comp.ratio),
            "Attack": norm_attack(comp.attack_ms),
            "Release": norm_release(comp.release_ms),
            "Knee": max(0.0, min(1.0, comp.knee_db / 72.0)),
            "Output Gain": max(0.0, min(1.0, 0.5 + comp.makeup_db / 48.0)),
        },
    }


def _ff_limiter(spec: MasteringChain) -> dict:
    """Pro-L 2 — set output ceiling. Style selects limiter character."""
    style_to_style = {
        "transparent": 0.0,   # Transparent
        "punchy": 0.2,        # Punchy
        "aggressive": 0.6,    # Aggressive
        "warm": 0.4,          # Warm
    }
    return {
        "name": "FabFilter Pro-L 2",
        "params": {
            "Output Level": max(0.0, min(1.0, 0.5 + spec.true_peak_db / 60.0)),
            "Style": style_to_style.get(spec.limiter_character, 0.0),
        },
    }


# ─────────────────────── Stereo width (suite-agnostic) ──────────────

def _stereo_width_fx(width: float) -> dict:
    """Use JS: 'Stereo Enhancer' (built into REAPER). Width 1.0 = neutral.

    If the preferred plugin is missing REAPER will fail to add it — that's
    fine, the chain continues without the width stage.
    """
    # 0.0 = mono, 0.5 = normal, 1.0 = max width
    # Map 0.8..1.4 → 0.5..0.85
    norm = 0.5 + (width - 1.0) * 0.5
    norm = max(0.0, min(1.0, norm))
    return {
        "name": "JS: Stereo Enhancer",
        "params_by_index": {0: norm},
    }
