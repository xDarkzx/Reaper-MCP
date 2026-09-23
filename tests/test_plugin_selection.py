"""Plugin selection: which plugin family the mix engine uses, per category.

The mix engine has parameter maps for two plugin families, stock REAPER and
FabFilter. It used to choose one family for everything from a single flag
(`detect_plugins`), so a user's per-category preference (say ReaEQ for EQ, or
a different compressor) never had any effect. Selection now works per
category (eq, compressor, reverb, limiter) from the inventory and the user's
preferences, and says so when it cannot honor a preference.
"""

from pathlib import Path

import pytest

from reaper_mcp.mix_engine import detect
from reaper_mcp.mix_engine.detect import PluginSuite
from reaper_mcp.mix_engine.plugins import (
    FabFilterProfile,
    ReaperStockProfile,
    get_plugin_profile_for,
)
from reaper_mcp.mix_engine.selection import (
    ENGINE_CATEGORIES,
    FAMILY_PLUGIN_NAMES,
    PluginSelection,
    describe_preference_support,
    family_for,
    select_plugins,
)

ROOT = Path(__file__).resolve().parent.parent

FAB = PluginSuite.FABFILTER
STOCK = PluginSuite.REAPER_STOCK

FABFILTER_INSTALLED = [
    "VST3: FabFilter Pro-Q 3 (FabFilter)",
    "VST3: FabFilter Pro-C 2 (FabFilter)",
    "VST3: FabFilter Pro-R (FabFilter)",
    "VST3: FabFilter Pro-L 2 (FabFilter)",
]
STOCK_INSTALLED = [
    "VST: ReaEQ (Cockos)",
    "VST: ReaComp (Cockos)",
    "VST: ReaVerbate (Cockos)",
    "VST: ReaLimit (Cockos)",
]


class _FakeClient:
    def __init__(self, installed):
        self.installed = installed

    async def execute(self, command, **params):
        assert command == "fx_list_installed"
        return {"data": {"plugins": [{"name": n} for n in self.installed]}}


@pytest.fixture
def prefs(monkeypatch):
    """Set the user's FX preferences for one test."""
    def _set(value):
        monkeypatch.setattr(detect, "load_user_fx_preferences", lambda: dict(value))
    _set({})
    return _set


# ---- which plugins each family can drive ---------------------------------

def test_the_supported_plugin_names_come_from_the_profiles_themselves():
    for category in ("eq", "compressor", "reverb"):
        assert FAMILY_PLUGIN_NAMES[FAB][category] == getattr(
            FabFilterProfile, "compressor_name" if category == "compressor" else f"{category}_name")
        assert FAMILY_PLUGIN_NAMES[STOCK][category] == getattr(
            ReaperStockProfile, "compressor_name" if category == "compressor" else f"{category}_name")
    assert set(FAMILY_PLUGIN_NAMES[FAB]) == set(ENGINE_CATEGORIES)
    assert set(FAMILY_PLUGIN_NAMES[STOCK]) == set(ENGINE_CATEGORIES)


@pytest.mark.parametrize("category,name,expected", [
    ("eq", "VST3: FabFilter Pro-Q 3 (FabFilter)", FAB),
    ("eq", "VST: ReaEQ (Cockos)", STOCK),
    ("compressor", "VST3: FabFilter Pro-C 2 (FabFilter)", FAB),
    ("compressor", "VST: ReaComp (Cockos)", STOCK),
    ("reverb", "VST3: FabFilter Pro-R (FabFilter)", FAB),
    ("reverb", "VST: ReaVerbate (Cockos)", STOCK),
    ("limiter", "VST3: FabFilter Pro-L 2 (FabFilter)", FAB),
    ("limiter", "VST: ReaLimit (Cockos)", STOCK),
    ("compressor", "VST3: TDR Kotelnikov (Tokyo Dawn Labs)", None),
    ("eq", "VST3: FabFilter Pro-Q 2 (FabFilter)", None),     # a different version
    ("compressor", "VST: ReaXcomp (Cockos)", None),          # not ReaComp
    ("eq", "VST3: FabFilter Pro-C 2 (FabFilter)", None),     # right vendor, wrong tool
])
def test_family_for_recognises_only_plugins_the_engine_can_drive(category, name, expected):
    assert family_for(category, name) == expected


# ---- selection from the inventory ----------------------------------------

@pytest.mark.asyncio
async def test_with_fabfilter_installed_and_no_preferences_everything_is_fabfilter(prefs):
    selection = await select_plugins(_FakeClient(FABFILTER_INSTALLED + STOCK_INSTALLED))
    assert all(selection.family(c) == FAB for c in ENGINE_CATEGORIES)
    assert selection.suite == FAB
    assert not selection.ignored_preferences


@pytest.mark.asyncio
async def test_with_only_stock_plugins_everything_is_stock(prefs):
    selection = await select_plugins(_FakeClient(STOCK_INSTALLED))
    assert all(selection.family(c) == STOCK for c in ENGINE_CATEGORIES)
    assert selection.suite == STOCK


@pytest.mark.asyncio
async def test_stock_is_never_used_while_a_third_party_plugin_is_installed(prefs):
    """REAPER's own plugins are a last resort, even when a preference names one."""
    prefs({"eq": "VST: ReaEQ (Cockos)"})
    selection = await select_plugins(_FakeClient(FABFILTER_INSTALLED + STOCK_INSTALLED))
    assert all(selection.family(c) == FAB for c in ENGINE_CATEGORIES)
    assert "REAPER stock" in selection.ignored_preferences["eq"]


@pytest.mark.asyncio
async def test_a_stock_preference_is_honored_when_no_third_party_plugin_exists(prefs):
    prefs({"eq": "VST: ReaEQ (Cockos)"})
    selection = await select_plugins(_FakeClient(STOCK_INSTALLED))
    assert selection.family("eq") == STOCK
    assert not selection.ignored_preferences


@pytest.mark.asyncio
async def test_a_preference_for_one_category_changes_only_that_category(prefs):
    """A supported third-party plugin can still be chosen per category."""
    installed = FABFILTER_INSTALLED + STOCK_INSTALLED
    prefs({"limiter": "VST3: FabFilter Pro-L 2 (FabFilter)"})
    selection = await select_plugins(_FakeClient(installed))
    assert selection.family("limiter") == FAB
    assert not selection.ignored_preferences


@pytest.mark.asyncio
async def test_a_preference_for_a_plugin_the_engine_cannot_drive_is_reported(prefs):
    prefs({"compressor": "VST3: TDR Kotelnikov (Tokyo Dawn Labs)"})
    installed = FABFILTER_INSTALLED + STOCK_INSTALLED + ["VST3: TDR Kotelnikov (Tokyo Dawn Labs)"]
    selection = await select_plugins(_FakeClient(installed))
    assert "compressor" in selection.ignored_preferences
    reason = selection.ignored_preferences["compressor"]
    assert "TDR Kotelnikov" in reason and "parameter map" in reason
    assert selection.family("compressor") == FAB       # falls back, not stuck


@pytest.mark.asyncio
async def test_an_unsupported_preference_falls_back_to_stock_when_fabfilter_is_missing(prefs):
    prefs({"compressor": "VST3: TDR Kotelnikov (Tokyo Dawn Labs)"})
    installed = STOCK_INSTALLED + ["VST3: TDR Kotelnikov (Tokyo Dawn Labs)"]
    selection = await select_plugins(_FakeClient(installed))
    assert selection.family("compressor") == STOCK


@pytest.mark.asyncio
async def test_a_preference_for_a_plugin_that_is_not_installed_is_reported(prefs):
    prefs({"eq": "VST3: FabFilter Pro-Q 3 (FabFilter)"})
    selection = await select_plugins(_FakeClient(STOCK_INSTALLED))
    assert "not installed" in selection.ignored_preferences["eq"]
    assert selection.family("eq") == STOCK


@pytest.mark.asyncio
async def test_categories_the_engine_does_not_place_are_not_reported_as_ignored(prefs):
    prefs({"deesser": "Some De-esser"})
    selection = await select_plugins(_FakeClient(STOCK_INSTALLED))
    assert "deesser" not in selection.ignored_preferences


@pytest.mark.asyncio
async def test_a_broken_inventory_defaults_to_stock_instead_of_failing(prefs, monkeypatch):
    async def boom(client):
        raise RuntimeError("REAPER unreachable")
    monkeypatch.setattr(detect, "get_inventory", boom)
    selection = await select_plugins(_FakeClient([]))
    assert selection.suite == STOCK


# ---- the profile built from a selection ----------------------------------

def test_the_composite_profile_uses_each_categorys_own_family():
    selection = PluginSelection(
        families={"eq": STOCK, "compressor": FAB, "reverb": STOCK, "limiter": FAB},
        ignored_preferences={},
    )
    profile = get_plugin_profile_for(selection)
    eq = profile.eq_fx_chain_entry({"bands": []})
    comp = profile.compression_fx_chain_entry({"ratio": 3.0, "threshold_db": -18, "attack_ms": 10,
                                               "release_ms": 100, "makeup_db": 0})
    reverb = profile.reverb_fx_chain_entry({"room_size": 0.5, "dampening": 0.5})
    assert eq["name"] == ReaperStockProfile.eq_name
    assert comp["name"] == FabFilterProfile.compressor_name
    assert reverb["name"] == ReaperStockProfile.reverb_name


def test_a_uniform_selection_matches_the_old_single_suite_behaviour():
    for suite, profile_class in ((FAB, FabFilterProfile), (STOCK, ReaperStockProfile)):
        selection = PluginSelection.uniform(suite)
        entry = get_plugin_profile_for(selection).eq_fx_chain_entry({"bands": []})
        assert entry["name"] == profile_class.eq_name
        assert selection.suite == suite


def test_the_summary_reports_the_families_and_any_ignored_preferences():
    selection = PluginSelection(
        families={"eq": STOCK, "compressor": FAB, "reverb": FAB, "limiter": FAB},
        ignored_preferences={"limiter": "not installed"},
    )
    summary = selection.summary()
    assert summary["plugin_suite"] == "fabfilter"
    assert summary["plugin_families"]["eq"] == "reaper_stock"
    assert summary["preferences_ignored"] == {"limiter": "not installed"}
    assert "preferences_ignored" not in PluginSelection.uniform(STOCK).summary()


# ---- the master chain follows the selection ------------------------------

def _master_spec():
    import reaper_mcp.mix_engine.catalog  # noqa: F401 - registers the styles
    from reaper_mcp.mix_engine.profiles_v2 import get_profile
    return get_profile("hiphop").mastering


def test_the_master_chain_builds_each_stage_from_its_own_family():
    from reaper_mcp.mix_engine.master import _build_master_fx_chain
    selection = PluginSelection(
        families={"eq": STOCK, "compressor": FAB, "reverb": FAB, "limiter": STOCK},
        ignored_preferences={},
    )
    names = [e["name"] for e in _build_master_fx_chain(_master_spec(), selection)]
    assert names[0] == ReaperStockProfile.eq_name                      # subtractive EQ
    assert FabFilterProfile.compressor_name in names                   # bus glue
    assert names[-1] == FAMILY_PLUGIN_NAMES[STOCK]["limiter"]          # limiter


@pytest.mark.parametrize("suite", [FAB, STOCK])
def test_the_master_limiter_name_matches_what_selection_says_it_can_drive(suite):
    from reaper_mcp.mix_engine.master import _build_master_fx_chain
    chain = _build_master_fx_chain(_master_spec(), PluginSelection.uniform(suite))
    assert chain[-1]["name"] == FAMILY_PLUGIN_NAMES[suite]["limiter"]


# ---- setting preferences tells you what the engine can do with them ------

def test_setting_preferences_reports_what_the_engine_can_drive():
    report = describe_preference_support({
        "eq": "VST: ReaEQ (Cockos)",
        "compressor": "Waves SSL G-Master Buss Compressor",
        "deesser": "Some De-esser",
    })
    assert report["eq"]["supported"] is True and report["eq"]["family"] == "reaper_stock"
    assert "only used when no supported third-party" in report["eq"]["note"]
    assert report["compressor"]["supported"] is False
    assert "parameter map" in report["compressor"]["note"]
    assert report["deesser"]["supported"] is False
    assert "doesn't place" in report["deesser"]["note"]


def test_the_set_fx_preferences_tool_returns_the_engine_support_report():
    source = (ROOT / "reaper_mcp" / "tools" / "inventory_tools.py").read_text(encoding="utf-8")
    assert '"engine_support": describe_preference_support(saved)' in source
    assert "Mix pipelines consult" not in source     # the old, untrue claim


# ---- every pipeline goes through the selection ---------------------------

@pytest.mark.parametrize("relative", [
    "reaper_mcp/mix_engine/__init__.py",
    "reaper_mcp/mix_engine/master.py",
    "reaper_mcp/mix_engine/fix_mix.py",
    "reaper_mcp/tools/pipeline_tools.py",
])
def test_pipelines_select_plugins_per_category(relative):
    source = (ROOT / relative).read_text(encoding="utf-8")
    assert "select_plugins(client)" in source
    assert "selection.summary()" in source


# ---- detect_plugins is gone ----------------------------------------------

def test_detect_plugins_no_longer_exists_anywhere():
    assert not hasattr(detect, "detect_plugins")
    for path in (ROOT / "reaper_mcp").rglob("*.py"):
        assert "detect_plugins" not in path.read_text(encoding="utf-8"), path
