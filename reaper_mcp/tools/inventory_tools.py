"""FX inventory tools — show the AI what plugins are installed + manage user prefs."""

import json
import logging

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode

logger = logging.getLogger(__name__)


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def fx_list_installed(category: str = "", full_list: bool = False) -> dict:
        """List every FX plugin installed in REAPER, grouped by category.

        Uses REAPER's EnumInstalledFX API. Returns:
          - `all_installed`: raw list of plugin names — capped at 150 unless
            `full_list=True` (power users can have 500+ installed; the
            `best_*` picks below already cover the decision the AI actually
            needs to make, so the raw list is capped by default to avoid
            dumping the whole catalog into context on every call)
          - `best_eq` / `best_compressor` / `best_reverb` / `best_limiter` /
            `best_deesser` / `best_gate` / `best_saturator` / `best_multiband` /
            `best_stereo`: highest-ranked plugin per category that the user has
          - `racks_detected`: any rack-style plugins (StudioRack, PatchWork, Lion,
            Multipass, Snap Heap) — the MCP does NOT configure modules inside
            racks, so avoid routing auto-mixing through them
          - `user_overrides`: current contents of the preferences file

        Use this BEFORE running mix pipelines to know what the user has.
        If the user has premium plugins (FabFilter, Waves, iZotope, Valhalla,
        Softube, etc.), prefer those over REAPER stock.

        Args:
            category: Optional — filter output to a single category:
                      "eq", "compressor", "limiter", "reverb", "deesser",
                      "gate", "saturator", "multiband", "stereo".
                      Empty returns full inventory.
            full_list: Return the complete `all_installed` list uncapped.
                       Only needed if you're hunting for something the
                       built-in category rankings don't cover.
        """
        from reaper_mcp.mix_engine.detect import get_inventory
        from reaper_mcp.mix_engine.fx_inventory import CATEGORY_RANKINGS, best_for_category

        inv = await get_inventory(client)

        if category:
            cat = category.strip().lower()
            if cat not in CATEGORY_RANKINGS:
                raise ReaperMCPError(
                    ErrorCode.INVALID_PARAMETER,
                    f"Unknown category {category!r}. "
                    f"Valid: {sorted(CATEGORY_RANKINGS.keys())}",
                )
            pick = getattr(inv, f"best_{cat}", None) or best_for_category(cat, inv.all_installed)
            # Also list all plugins matching any rank in the category
            ranking = CATEGORY_RANKINGS[cat]
            matches = []
            installed_low = [n.lower() for n in inv.all_installed]
            for pref in ranking:
                pl = pref.lower()
                for orig, lo in zip(inv.all_installed, installed_low):
                    if pl in lo and orig not in matches:
                        matches.append(orig)
            return {
                "category": cat,
                "best": pick,
                "available": matches,
                "user_override": inv.user_overrides.get(cat),
            }

        result = inv.to_dict()
        total = len(result.get("all_installed", []))
        if not full_list and total > 150:
            result["all_installed"] = result["all_installed"][:150]
            result["all_installed_truncated"] = True
            result["all_installed_total"] = total
        return result

    @mcp.tool()
    async def set_fx_preferences(preferences: str) -> dict:
        """Save user FX preferences — per-category plugin overrides.

        Stored at `%APPDATA%/reaper_mcp/fx_prefs.json` (Windows) or
        `~/.reaper_mcp/fx_prefs.json` (macOS/Linux). Mix pipelines consult
        this before auto-picking.

        Args:
            preferences: JSON object mapping categories to plugin names, e.g.
                `{"eq": "FabFilter Pro-Q 3", "compressor": "Waves SSL G-Master Buss Compressor",
                  "reverb": "Valhalla VintageVerb", "limiter": "FabFilter Pro-L 2"}`

        Categories: eq, compressor, limiter, reverb, deesser, gate, saturator,
                    multiband, stereo. Plugin names must match what REAPER
                    reports (check `fx_list_installed` first).
        """
        try:
            prefs = json.loads(preferences)
        except (json.JSONDecodeError, TypeError) as e:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                 f"preferences must be a JSON object: {e}")
        if not isinstance(prefs, dict):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                 "preferences must be a JSON object mapping category -> plugin name")

        from reaper_mcp.mix_engine.detect import save_user_fx_preferences
        from reaper_mcp.mix_engine.fx_inventory import CATEGORY_RANKINGS

        # Warn about unknown keys (don't error — user may be adding custom categories later)
        unknown = [k for k in prefs if k not in CATEGORY_RANKINGS]
        if unknown:
            logger.info("Ignoring unknown FX preference keys: %s", unknown)

        path = save_user_fx_preferences(prefs)
        return {
            "success": True,
            "path": path,
            "saved": {k: v for k, v in prefs.items() if k in CATEGORY_RANKINGS},
            "ignored": unknown,
        }
