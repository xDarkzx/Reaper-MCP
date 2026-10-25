"""The mix engine leaves the user's own FX and tracks alone.

Found while verifying issue #44 on a real project:
- engine_master / engine_mix with clean=True fell back to deleting FX by
  name (Pro-Q 3, Pro-C 2, Pro-L, ReaEQ...) whenever no "[MIX] "-tagged FX
  were present, which would wipe a hand-built FabFilter master chain.
- engine_fix_mix added untagged FX, so it depended on that fallback.
- A reverb return named "Plate Reverb (Vocals)" got lead-vocal EQ/comp, and
  plain "Guitar"/"Bass" tracks matched no role in the rock styles.
"""

import json
from pathlib import Path

import pytest

import reaper_mcp.mix_engine.catalog  # noqa: F401  (registers styles)
from reaper_mcp.mix_engine import _MIX_FX_PREFIX, _clean_mix_fx_generic
from reaper_mcp.mix_engine.profiles_v2 import get_profile, is_bus_track, resolve_roles

LUA_SRC = Path(__file__).resolve().parent.parent / "reaper_scripts" / "reaper_mcp_server.lua"

DEMO_TRACKS = [
    {"index": i, "name": n, "item_count": items, "receive_count": recv}
    for i, (n, items, recv) in enumerate([
        ("Guitar", 1, 0), ("Bass", 1, 0), ("Drums", 1, 0), ("Vocals", 1, 0),
        ("Piano", 1, 0), ("Other", 1, 0), ("Plate Reverb (Vocals)", 0, 1),
    ])
]


# ---- clean only removes engine-tagged FX ------------------------------------

class _ChainClient:
    def __init__(self, chain):
        self.chain = chain
        self.calls = []

    async def execute(self, command, **params):
        self.calls.append((command, params))
        if command == "fx_get_chain":
            return {"data": {"fx_chain": self.chain}}
        if command == "track_get_all":
            return {"data": {"tracks": []}}
        return {"data": {}}


@pytest.mark.asyncio
async def test_track_clean_never_removes_untagged_user_fx():
    client = _ChainClient([
        {"index": 0, "name": "VST3: FabFilter Pro-Q 3 (FabFilter)"},
        {"index": 1, "name": "VST: ReaComp (Cockos)"},
    ])
    await _clean_mix_fx_generic(client, [0])
    assert not any(c[0] == "fx_remove_batch" for c in client.calls)


@pytest.mark.asyncio
async def test_track_clean_removes_only_tagged_fx():
    client = _ChainClient([
        {"index": 0, "name": "VST3: FabFilter Pro-Q 3 (FabFilter)"},
        {"index": 1, "name": f"{_MIX_FX_PREFIX}ReaEQ"},
    ])
    await _clean_mix_fx_generic(client, [0])
    removals = [json.loads(c[1]["entries"]) for c in client.calls if c[0] == "fx_remove_batch"]
    assert removals == [[{"track_index": 0, "fx_indices": [1]}]]


def _run_master_clean(names):
    lupa = pytest.importorskip("lupa")
    source = LUA_SRC.read_text(encoding="utf-8")
    start = source.index("function compose.setup_master_chain(p)")
    end = source.index("\nend\n", start)
    rt = lupa.LuaRuntime()
    rt.execute("""
    compose = {}
    function json_decode(s) return nil end
    function apply_named_config() return {} end
    chain = {}
    reaper = {
      GetMasterTrack = function() return "MASTER" end,
      Undo_BeginBlock = function() end, Undo_EndBlock = function() end,
      PreventUIRefresh = function() end, UpdateArrange = function() end,
      TrackFX_GetCount = function() return #chain end,
      TrackFX_GetFXName = function(tr, fi) return true, chain[fi + 1] end,
      TrackFX_Delete = function(tr, fi) table.remove(chain, fi + 1) end,
    }
    """)
    for n in names:
        rt.execute(f"chain[#chain+1] = {json.dumps(n)}")
    rt.execute(source[start:end] + "\nend\n")
    rt.eval("compose.setup_master_chain")(rt.table_from({"clean": True}))
    return list(rt.eval("chain").values())


def test_master_clean_keeps_user_fabfilter_chain():
    user_chain = ["VST3: FabFilter Pro-Q 3 (FabFilter)", "VST3: FabFilter Pro-C 2 (FabFilter)",
                  "VST3: FabFilter Saturn (FabFilter)", "VST3: FabFilter Pro-L 2 (FabFilter)"]
    assert _run_master_clean(user_chain) == user_chain


def test_master_clean_removes_only_tagged_fx():
    left = _run_master_clean(["VST3: FabFilter Pro-L 2 (FabFilter)", "[MIX] ReaEQ", "[MIX] ReaLimit"])
    assert left == ["VST3: FabFilter Pro-L 2 (FabFilter)"]


# ---- role resolution ---------------------------------------------------------

def test_plain_guitar_and_bass_resolve_in_rock():
    roles = resolve_roles(get_profile("alt_rock"), DEMO_TRACKS)
    assert roles[0] == "rhythm_guitar"
    assert roles[1] == "bass_guitar"


def test_reverb_return_is_not_given_an_instrument_role():
    assert is_bus_track(DEMO_TRACKS[6])
    assert 6 not in resolve_roles(get_profile("alt_rock"), DEMO_TRACKS)


def test_generic_name_never_lands_on_a_role_the_style_lacks():
    # swing_jazz has no guitar role and no full-kit drums role.
    roles = resolve_roles(get_profile("swing_jazz"), DEMO_TRACKS)
    assert 0 not in roles and 2 not in roles
    assert roles[1] == "upright_bass"


def test_style_alias_still_beats_generic_name():
    tracks = [{"index": 0, "name": "Lead Gtr", "item_count": 1, "receive_count": 0}]
    assert resolve_roles(get_profile("alt_rock"), tracks)[0] == "lead_guitar"


def test_track_without_counts_is_not_treated_as_bus():
    assert not is_bus_track({"index": 0, "name": "Vocals"})


# ---- fix_mix tags its FX and skips returns ----------------------------------

class _FixMixClient:
    def __init__(self):
        self.calls = {}

    async def execute(self, command, **params):
        self.calls.setdefault(command, []).append(params)
        if command == "track_get_all":
            return {"data": {"tracks": DEMO_TRACKS}}
        return {"data": {}}


@pytest.mark.asyncio
async def test_fix_mix_tags_fx_and_skips_reverb_return(monkeypatch):
    from reaper_mcp.mix_engine import fix_mix
    from reaper_mcp.mix_engine.detect import PluginSuite
    from reaper_mcp.mix_engine.selection import PluginSelection

    async def stock(_client):
        return PluginSelection.uniform(PluginSuite.REAPER_STOCK)

    monkeypatch.setattr(fix_mix, "select_plugins", stock)
    client = _FixMixClient()
    await fix_mix.run_fix_mix(client, style="alt_rock")

    tracks = json.loads(client.calls["setup_fx_chain"][0]["tracks"])
    assert 6 not in [t["track_index"] for t in tracks]
    assert all(fx["renamed_name"].startswith(_MIX_FX_PREFIX)
               for t in tracks for fx in t["fx_chain"])
    master = json.loads(client.calls["setup_master_chain"][0]["fx_chain"])
    assert master and all(fx["renamed_name"].startswith(_MIX_FX_PREFIX) for fx in master)
