"""Plugin selection — which plugin family the mix engine drives, per category.

The mix engine has parameter maps for two plugin families, stock REAPER and
FabFilter. A single global flag used to choose one family for everything, so a
user's per-category preference (ReaEQ for EQ, a different compressor...) never
had any effect. Selection works per category instead: it starts from the
inventory (`get_inventory`, which already applies the user's preferences) and
resolves each category the engine places (eq, compressor, reverb, limiter) to
the family whose parameter map can drive the chosen plugin.

REAPER's own plugins are a last resort: they are used for a category only when
no supported third-party plugin is installed for it, even if a preference names
one.

A preference for a plugin the engine has no parameter map for, or that is not
installed, cannot be honored. The engine then uses the best supported plugin
for that category and says so, instead of silently ignoring the preference.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from reaper_mcp.mix_engine import detect
from reaper_mcp.mix_engine.detect import PluginInventory, PluginSuite
from reaper_mcp.mix_engine.plugins import FabFilterProfile, ReaperStockProfile

logger = logging.getLogger(__name__)

# The categories the mix and master pipelines place plugins for.
ENGINE_CATEGORIES = ("eq", "compressor", "reverb", "limiter")

# Which plugin each family drives for each category, taken from the profile
# classes themselves so there is one source of truth for the names.
FAMILY_PLUGIN_NAMES: dict[PluginSuite, dict[str, str]] = {
    family: {
        "eq": profile.eq_name,
        "compressor": profile.compressor_name,
        "reverb": profile.reverb_name,
        "limiter": profile.limiter_name,
    }
    for family, profile in (
        (PluginSuite.FABFILTER, FabFilterProfile),
        (PluginSuite.REAPER_STOCK, ReaperStockProfile),
    )
}


def family_for(category: str, plugin_name: str) -> Optional[PluginSuite]:
    """The family whose parameter map drives `plugin_name` for `category`, or
    None if the engine has no map for it (a different plugin, or a different
    version of the same one)."""
    lowered = plugin_name.lower()
    for family, names in FAMILY_PLUGIN_NAMES.items():
        expected = names.get(category)
        if expected and expected.lower() in lowered:
            return family
    return None


def _fallback_family(category: str, installed: list[str]) -> PluginSuite:
    """Best supported family for a category: FabFilter's plugin if installed,
    otherwise REAPER's own (always present)."""
    fabfilter = FAMILY_PLUGIN_NAMES[PluginSuite.FABFILTER][category].lower()
    if any(fabfilter in name.lower() for name in installed):
        return PluginSuite.FABFILTER
    return PluginSuite.REAPER_STOCK


@dataclass
class PluginSelection:
    """Which plugin family each engine category uses, and any preference that
    could not be honored (category -> reason)."""

    families: dict[str, PluginSuite]
    ignored_preferences: dict[str, str] = field(default_factory=dict)
    inventory: Optional[PluginInventory] = None

    @classmethod
    def uniform(cls, suite: PluginSuite) -> "PluginSelection":
        """Every category uses the same family."""
        return cls(families={category: suite for category in ENGINE_CATEGORIES})

    def family(self, category: str) -> PluginSuite:
        return self.families[category]

    @property
    def suite(self) -> PluginSuite:
        """Single-flag summary for responses: FabFilter if any category uses it."""
        if any(f == PluginSuite.FABFILTER for f in self.families.values()):
            return PluginSuite.FABFILTER
        return PluginSuite.REAPER_STOCK

    def summary(self) -> dict:
        """Fields every pipeline adds to its response."""
        result = {
            "plugin_suite": self.suite.value,
            "plugin_families": {c: f.value for c, f in self.families.items()},
        }
        if self.ignored_preferences:
            result["preferences_ignored"] = dict(self.ignored_preferences)
        return result


def resolve_selection(inventory: PluginInventory) -> PluginSelection:
    """Resolve each engine category to a plugin family from the inventory."""
    installed = inventory.all_installed
    families: dict[str, PluginSuite] = {}
    ignored: dict[str, str] = {}

    for category in ENGINE_CATEGORIES:
        pick = getattr(inventory, f"best_{category}")
        preference = inventory.user_overrides.get(category)
        family = family_for(category, pick) if pick else None
        if family is None:
            family = _fallback_family(category, installed)
        stock_overridden = False
        if family == PluginSuite.REAPER_STOCK and _fallback_family(category, installed) == PluginSuite.FABFILTER:
            # REAPER's own plugins are only a last resort: never pick them
            # while a supported third-party plugin is installed.
            family = PluginSuite.FABFILTER
            stock_overridden = True
        used = FAMILY_PLUGIN_NAMES[family][category]

        if preference:
            if stock_overridden and family_for(category, preference) == PluginSuite.REAPER_STOCK:
                ignored[category] = (
                    f"'{preference}' is a REAPER stock plugin, which is only used when no "
                    f"supported third-party plugin is installed, so {used} was used instead"
                )
            elif pick != preference:
                # The inventory only keeps a preference that is installed.
                ignored[category] = f"'{preference}' is not installed, so {used} was used instead"
            elif family_for(category, preference) is None:
                ignored[category] = (
                    f"the mix engine has no parameter map for '{preference}', "
                    f"so {used} was used instead"
                )
        families[category] = family

    return PluginSelection(families=families, ignored_preferences=ignored, inventory=inventory)


async def select_plugins(client) -> PluginSelection:
    """Query REAPER for what is installed and select a family per category.
    If that fails, default to REAPER's own plugins rather than fail the mix."""
    try:
        inventory = await detect.get_inventory(client)
    except Exception as exc:
        logger.warning("Plugin selection failed: %s - defaulting to REAPER stock", exc)
        return PluginSelection.uniform(PluginSuite.REAPER_STOCK)
    return resolve_selection(inventory)


def describe_preference_support(preferences: dict[str, str]) -> dict[str, dict]:
    """For each saved preference, whether the mix engine can drive it."""
    report: dict[str, dict] = {}
    for category, plugin in preferences.items():
        if category not in ENGINE_CATEGORIES:
            report[category] = {
                "supported": False,
                "note": "the mix engine doesn't place this category, so the preference has no effect on it",
            }
            continue
        family = family_for(category, plugin)
        if family is None:
            report[category] = {
                "supported": False,
                "note": (
                    f"the mix engine has no parameter map for '{plugin}'; "
                    "it will use the best supported plugin for this category instead"
                ),
            }
        elif family == PluginSuite.REAPER_STOCK:
            report[category] = {
                "supported": True,
                "family": family.value,
                "note": (
                    "REAPER stock plugins are only used when no supported third-party "
                    "plugin is installed for this category"
                ),
            }
        else:
            report[category] = {"supported": True, "family": family.value}
    return report
