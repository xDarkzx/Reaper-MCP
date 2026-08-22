"""VST/AU parameter auto-scan cache: infers each parameter's units and curve
shape from REAPER's own formatted display strings, and caches the result per
plugin so a plugin only ever needs to be scanned once (see fx_scan_params in
reaper_mcp/tools/fx_tools.py and the design doc at
docs/superpowers/specs/2026-08-06-vst-param-autoscan-design.md).
"""

import json
import os
import re
import time

from reaper_mcp_shared.constants import PLUGIN_MAP_DIR


def sanitize_plugin_name(name: str) -> str:
    """Turn a raw FX name like 'VST3: Pro-Q 3 (FabFilter)' into a safe filename stem."""
    safe = re.sub(r"[^A-Za-z0-9]+", "_", name.strip())
    return safe.strip("_").lower()


_NUMBER_RE = re.compile(r"\s*([-+]?\d+\.?\d*)\s*([a-zA-Z%]*)")
_UNIT_MULTIPLIERS = {"k": 1000.0, "m": 0.001}


def _parse_numeric(s: str):
    """Extract (number, unit) from a formatted display string, or (None, None)
    if it doesn't start with a number (e.g. 'Off', 'Bypass')."""
    m = _NUMBER_RE.match(s)
    if not m or not m.group(1):
        return None, None
    return float(m.group(1)), m.group(2)


def _normalize(num: float, unit: str):
    """Fold a k/m unit prefix into the number so '20 kHz' and '632 Hz' are comparable."""
    if unit and len(unit) > 1 and unit[0].lower() in _UNIT_MULTIPLIERS:
        return num * _UNIT_MULTIPLIERS[unit[0].lower()], unit[1:]
    return num, unit


def infer_curve(samples: list, step_count: int | None = None) -> tuple:
    """Infer a parameter's curve shape from its sampled points.

    `samples` is a list of either plain formatted-display strings (older
    shape) or {"normalized": float, "formatted": str} dicts (current Lua
    handler output) — either works, since only the formatted string is
    used here for classification.

    `step_count` is REAPER's own TrackFX_GetParameterStepCount for this
    param, when available: a positive value means REAPER itself reports
    this as a genuinely discrete/stepped parameter, which settles the
    classification directly instead of guessing from string patterns —
    the guess-based path below is a fallback for when that API doesn't
    give a definitive answer (step_count is None or 0, e.g. a boolean
    toggle, which the non-numeric-string check below still catches).

    Returns (curve_type, unit) where curve_type is one of "linear",
    "logarithmic", "stepped", or "unknown". "unknown" is a valid, expected
    outcome (e.g. a constant-value param) — not an error. Works with
    however many points were actually sampled (previously hardcoded to
    exactly 3 — real params can now be sampled far more densely, e.g.
    every discrete step of a stepped param, or 9 points for continuous
    ones)."""
    if step_count is not None and step_count > 0:
        return "stepped", None

    formatted = [s["formatted"] if isinstance(s, dict) else s for s in samples]
    parsed = [_parse_numeric(s) for s in formatted]
    numeric_count = sum(1 for num, _ in parsed if num is not None)

    if numeric_count == 0:
        return "stepped", None
    if numeric_count < len(formatted):
        return "unknown", None

    normalized = [_normalize(num, unit) for num, unit in parsed]
    values = [v for v, _ in normalized]
    units = [u for _, u in normalized]
    unit = units[0] if len(set(units)) == 1 else None

    if len(set(values)) == 1:
        return "unknown", unit

    diffs = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    span = abs(values[-1] - values[0]) or 1.0
    if max(diffs) - min(diffs) <= 0.15 * span:
        return "linear", unit

    if all(v != 0 for v in values[:-1]):
        ratios = [values[i + 1] / values[i] for i in range(len(values) - 1)]
        if all(r > 0 for r in ratios) and max(ratios) - min(ratios) <= 0.15 * max(ratios):
            return "logarithmic", unit

    return "unknown", unit


def load_cached_map(plugin_name: str):
    """Return the cached scan for this plugin, or None if never scanned or corrupt."""
    path = os.path.join(PLUGIN_MAP_DIR, sanitize_plugin_name(plugin_name) + ".json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_cached_map(plugin_name: str, params: list, truncated: bool) -> None:
    """Write a scan result to the cache. Best-effort: a write failure here
    must never break the scan response the caller already has in hand."""
    try:
        os.makedirs(PLUGIN_MAP_DIR, exist_ok=True)
        record = {
            "plugin_name": plugin_name,
            "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "truncated": truncated,
            "params": params,
        }
        path = os.path.join(PLUGIN_MAP_DIR, sanitize_plugin_name(plugin_name) + ".json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        os.replace(tmp, path)
    except Exception:  # noqa: S110 - best-effort cache write, see docstring
        pass
