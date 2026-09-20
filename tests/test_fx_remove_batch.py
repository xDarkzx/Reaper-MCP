"""fx_remove_batch: one call removes one FX, several, or a whole chain,
across one or many tracks (master included as track_index -1).

It replaces the single-FX fx_remove tool. The validator normalises entries,
the Lua handler resolves and deletes them, and the mix engine's cleanup makes
a single batch call per track instead of one call per FX.
"""

import json
from pathlib import Path

import pytest

from reaper_mcp.mix_engine import _MIX_FX_PREFIX, _clean_mix_fx_generic
from reaper_mcp.tools.fx_tools import _normalize_fx_remove_entries
from reaper_mcp_shared.error_codes import ErrorCode, ReaperMCPError

ROOT = Path(__file__).resolve().parent.parent
LUA = ROOT / "reaper_scripts" / "reaper_mcp_server.lua"


def _lua_handler() -> str:
    source = LUA.read_text(encoding="utf-8")
    start = source.index("function fx.fx_remove_batch(p)")
    return source[start: source.index("\nend\n", start)]


# ---- validator ------------------------------------------------------------

def test_all_selector_is_passed_through():
    assert _normalize_fx_remove_entries([{"track_index": -1, "all": True}]) == [
        {"track_index": -1, "all": True}
    ]


def test_single_fx_index_becomes_a_one_item_list():
    assert _normalize_fx_remove_entries([{"track_index": 2, "fx_index": 3}]) == [
        {"track_index": 2, "fx_indices": [3]}
    ]


def test_fx_indices_are_deduplicated_and_sorted_highest_first():
    result = _normalize_fx_remove_entries([{"track_index": 0, "fx_indices": [1, 4, 1, 3]}])
    assert result == [{"track_index": 0, "fx_indices": [4, 3, 1]}]


def test_many_tracks_and_master_in_one_batch():
    entries = [
        {"track_index": -1, "all": True},
        {"track_index": 0, "fx_indices": [0, 2]},
        {"track_index": 5, "fx_index": 1},
    ]
    assert len(_normalize_fx_remove_entries(entries)) == 3


@pytest.mark.parametrize("entries", [
    [],
    "not a list",
    [{"fx_index": 1}],                                        # no track_index
    [{"track_index": 0}],                                     # no selector
    [{"track_index": 0, "all": True, "fx_index": 1}],         # two selectors
    [{"track_index": 0, "all": False}],                       # all must be true
    [{"track_index": 0, "fx_index": -1}],
    [{"track_index": 0, "fx_index": True}],                   # bool is not an index
    [{"track_index": 0, "fx_indices": []}],
    [{"track_index": 0, "fx_indices": [1, "2"]}],
    [{"track_index": True, "all": True}],
    [{"track_index": "0", "all": True}],
    ["not a dict"],
])
def test_malformed_entries_are_refused(entries):
    with pytest.raises(ReaperMCPError):
        _normalize_fx_remove_entries(entries)


def test_track_index_below_master_is_refused():
    with pytest.raises(ReaperMCPError) as raised:
        _normalize_fx_remove_entries([{"track_index": -2, "all": True}])
    assert raised.value.code == ErrorCode.VALUE_OUT_OF_RANGE


def test_entry_count_is_capped():
    entries = [{"track_index": 0, "fx_index": 0}] * 201
    with pytest.raises(ReaperMCPError) as raised:
        _normalize_fx_remove_entries(entries)
    assert raised.value.code == ErrorCode.VALUE_OUT_OF_RANGE


# ---- single tool is gone --------------------------------------------------

def test_single_fx_remove_is_gone_everywhere():
    for path in (ROOT / "reaper_mcp").rglob("*.py"):
        assert '"fx_remove"' not in path.read_text(encoding="utf-8"), path
    lua = LUA.read_text(encoding="utf-8")
    assert "function fx.fx_remove(" not in lua
    assert "function fx.fx_remove_batch(p)" in lua


# ---- Lua handler shape ----------------------------------------------------

def test_lua_resolves_targets_before_deleting_anything():
    body = _lua_handler()
    assert body.index("slot.targets") < body.index("reaper.Undo_BeginBlock()")
    assert body.index("reaper.Undo_BeginBlock()") < body.index("reaper.TrackFX_Delete")


def test_lua_deletes_highest_index_first():
    assert "return a > b" in _lua_handler()


def test_lua_uses_get_track_so_master_is_addressable():
    assert "get_track(e)" in _lua_handler()


def test_lua_records_bad_entries_instead_of_aborting():
    body = _lua_handler()
    assert "errors" in body and "out of range" in body


# ---- mix engine cleanup makes one batch call per track --------------------

class _FakeClient:
    def __init__(self, chains):
        self.chains = chains
        self.calls = []

    async def execute(self, command, **params):
        self.calls.append((command, params))
        if command == "fx_get_chain":
            return {"data": {"fx_chain": self.chains[params["track_index"]]}}
        if command == "track_get_all":
            return {"data": {"tracks": []}}
        return {"data": {}}


@pytest.mark.asyncio
async def test_cleanup_removes_all_tagged_fx_in_one_call():
    chain = [
        {"index": 0, "name": f"{_MIX_FX_PREFIX}ReaEQ"},
        {"index": 1, "name": "User Plugin"},
        {"index": 2, "name": f"{_MIX_FX_PREFIX}ReaComp"},
    ]
    client = _FakeClient({0: chain})
    await _clean_mix_fx_generic(client, [0])

    removals = [c for c in client.calls if c[0] == "fx_remove_batch"]
    assert len(removals) == 1
    entries = json.loads(removals[0][1]["entries"])
    assert entries == [{"track_index": 0, "fx_indices": [0, 2]}]
    assert not any(c[0] == "fx_remove" for c in client.calls)


@pytest.mark.asyncio
async def test_cleanup_makes_no_call_when_nothing_matches():
    client = _FakeClient({0: [{"index": 0, "name": "User Plugin"}]})
    await _clean_mix_fx_generic(client, [0])
    assert not any(c[0] == "fx_remove_batch" for c in client.calls)
