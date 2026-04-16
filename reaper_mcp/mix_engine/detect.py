"""Plugin detection — enumerate installed FX and rank per category.

Returns a `PluginInventory` with the best installed plugin per processing
category (EQ, compressor, reverb, limiter, de-esser, gate, saturator, etc.)
plus a list of rack-style plugins the user has (so callers know to route
around them since rack interiors are opaque to REAPER's FX API).

Legacy: `detect_plugins()` still returns a `PluginSuite` enum for code paths
that only care "FabFilter or stock?". New code should prefer `get_inventory()`.
"""

import logging
import os
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

from reaper_mcp.mix_engine.fx_inventory import (
    CATEGORY_RANKINGS, best_for_category, detect_racks,
)

logger = logging.getLogger(__name__)


class PluginSuite(Enum):
    FABFILTER = "fabfilter"
    REAPER_STOCK = "reaper_stock"

    @property
    def value(self):
        return self._value_


@dataclass
class PluginInventory:
    """Snapshot of what's installed + per-category best-available picks."""
    all_installed: list[str] = field(default_factory=list)
    # Per-category best plugin (name as REAPER reports it) — None if nothing matched.
    best_eq: Optional[str] = None
    best_compressor: Optional[str] = None
    best_limiter: Optional[str] = None
    best_reverb: Optional[str] = None
    best_deesser: Optional[str] = None
    best_gate: Optional[str] = None
    best_saturator: Optional[str] = None
    best_multiband: Optional[str] = None
    best_stereo: Optional[str] = None
    # Rack-style plugins detected — treat opaquely, don't try to nest-configure.
    racks_detected: list[str] = field(default_factory=list)
    # User overrides from prefs file, if any.
    user_overrides: dict[str, str] = field(default_factory=dict)
    # Legacy helper for code paths that still want a single suite flag.
    suite: PluginSuite = PluginSuite.REAPER_STOCK

    def to_dict(self) -> dict:
        d = asdict(self)
        d["suite"] = self.suite.value
        return d


# ────────────────────────────────────────────────────────────────
# User preferences file
# ────────────────────────────────────────────────────────────────

def _prefs_path() -> str:
    """Return the platform-appropriate path to the FX preferences file."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, "reaper_mcp", "fx_prefs.json")
    home = os.path.expanduser("~")
    return os.path.join(home, ".reaper_mcp", "fx_prefs.json")


def load_user_fx_preferences() -> dict[str, str]:
    """Load `{category: plugin_name}` overrides from the prefs file.

    Categories: eq, compressor, limiter, reverb, deesser, gate, saturator,
                multiband, stereo. Missing keys fall back to auto-detection.
    """
    path = _prefs_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not read FX preferences at %s: %s", path, e)
        return {}
    if not isinstance(data, dict):
        logger.warning("FX preferences file is not a JSON object; ignoring")
        return {}
    # Keep only recognized category keys with string values
    return {
        k: v for k, v in data.items()
        if k in CATEGORY_RANKINGS and isinstance(v, str) and v.strip()
    }


def save_user_fx_preferences(prefs: dict[str, str]) -> str:
    """Write `{category: plugin_name}` to the prefs file. Returns the path."""
    path = _prefs_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Keep only recognized category keys
    clean = {
        k: v for k, v in prefs.items()
        if k in CATEGORY_RANKINGS and isinstance(v, str) and v.strip()
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2)
    return path


# ────────────────────────────────────────────────────────────────
# Inventory builder
# ────────────────────────────────────────────────────────────────

async def get_inventory(client) -> PluginInventory:
    """Query REAPER for installed FX and build a `PluginInventory` with
    per-category picks. User preferences override auto-detection.
    """
    # 1. Enumerate all installed plugins via the Lua handler
    installed: list[str] = []
    try:
        result = await client.execute("fx_list_installed")
        data = result.get("data", result)
        for entry in data.get("plugins", []):
            name = entry.get("name") if isinstance(entry, dict) else None
            if isinstance(name, str) and name:
                installed.append(name)
    except Exception as e:
        logger.warning("fx_list_installed failed: %s — inventory will be empty", e)

    # 2. Load user preferences
    user_prefs = load_user_fx_preferences()

    # 3. Pick best per category (user override beats auto)
    def pick(cat: str) -> Optional[str]:
        if cat in user_prefs and user_prefs[cat] in installed:
            return user_prefs[cat]
        if cat in user_prefs:
            # User asked for a plugin they don't have — warn but fall back
            logger.warning(
                "User FX preference for %s=%r not found in installed plugins; "
                "falling back to auto-detection",
                cat, user_prefs[cat],
            )
        return best_for_category(cat, installed) if installed else None

    inv = PluginInventory(
        all_installed=installed,
        best_eq=pick("eq"),
        best_compressor=pick("compressor"),
        best_limiter=pick("limiter"),
        best_reverb=pick("reverb"),
        best_deesser=pick("deesser"),
        best_gate=pick("gate"),
        best_saturator=pick("saturator"),
        best_multiband=pick("multiband"),
        best_stereo=pick("stereo"),
        racks_detected=detect_racks(installed) if installed else [],
        user_overrides=user_prefs,
    )

    # 4. Back-compat suite flag — prefer FabFilter if any FabFilter tool picked
    fabby = any(
        v and "fabfilter" in v.lower()
        for v in (inv.best_eq, inv.best_compressor, inv.best_reverb, inv.best_limiter)
    )
    inv.suite = PluginSuite.FABFILTER if fabby else PluginSuite.REAPER_STOCK
    return inv


# ────────────────────────────────────────────────────────────────
# Legacy single-suite detector (kept so existing mix pipeline works)
# ────────────────────────────────────────────────────────────────

async def detect_plugins(client) -> PluginSuite:
    """Legacy detector — returns FABFILTER if Pro-Q 3 (or similar) is the best
    EQ pick; REAPER_STOCK otherwise. New code should call `get_inventory`.
    """
    try:
        inv = await get_inventory(client)
        return inv.suite
    except Exception as e:
        logger.warning("Plugin detection failed: %s — defaulting to stock", e)
        return PluginSuite.REAPER_STOCK
