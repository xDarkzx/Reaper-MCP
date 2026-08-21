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


_NUMBER_RE = re.compile(r"\s*(-?\d+\.?\d*)\s*([a-zA-Z%]*)")
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


def infer_curve(samples: list) -> tuple:
    """Infer a parameter's curve shape from 3 display strings sampled at
    normalized 0.0, 0.5, and 1.0.

    Returns (curve_type, unit) where curve_type is one of "linear",
    "logarithmic", "stepped", or "unknown". "unknown" is a valid, expected
    outcome (e.g. a constant-value param) — not an error.
    """
    parsed = [_parse_numeric(s) for s in samples]
    numeric_count = sum(1 for num, _ in parsed if num is not None)

    if numeric_count == 0:
        return "stepped", None
    if numeric_count < len(samples):
        return "unknown", None

    normalized = [_normalize(num, unit) for num, unit in parsed]
    values = [v for v, _ in normalized]
    units = [u for _, u in normalized]
    unit = units[0] if len(set(units)) == 1 else None

    v0, v1, v2 = values
    if v0 == v1 == v2:
        return "unknown", unit

    diff1 = v1 - v0
    diff2 = v2 - v1
    span = abs(v2 - v0) or 1.0

    if abs(diff1 - diff2) <= 0.15 * span:
        return "linear", unit

    if v0 != 0 and v1 != 0:
        ratio1 = v1 / v0
        ratio2 = v2 / v1
        if ratio1 > 0 and ratio2 > 0 and abs(ratio1 - ratio2) <= 0.15 * max(ratio1, ratio2):
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
