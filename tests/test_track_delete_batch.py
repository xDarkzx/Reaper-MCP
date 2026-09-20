"""track_delete_batch: one call deletes one track, several, or all of them.

It replaces the single-track track_delete tool. Entries name their targets by
the numbering at the start of the call; the Lua handler resolves them first
and deletes highest-first, so one delete can never shift another's index.
The master track is never deletable.
"""

import json
from pathlib import Path

import pytest

from reaper_mcp.mix_engine import _REVERB_BUS_PREFIX, _clean_mix_fx_generic
from reaper_mcp.tools.track_tools import _normalize_track_delete_entries
from reaper_mcp_shared.error_codes import ErrorCode, ReaperMCPError

ROOT = Path(__file__).resolve().parent.parent
LUA = ROOT / "reaper_scripts" / "reaper_mcp_server.lua"


# ---- validator ------------------------------------------------------------

def test_all_selector_is_passed_through():
    assert _normalize_track_delete_entries([{"all": True}]) == [{"all": True}]


def test_single_track_index_becomes_a_one_item_list():
    assert _normalize_track_delete_entries([{"track_index": 3}]) == [{"track_indices": [3]}]


def test_track_indices_are_deduplicated_and_sorted_highest_first():
    result = _normalize_track_delete_entries([{"track_indices": [1, 4, 1, 3]}])
    assert result == [{"track_indices": [4, 3, 1]}]


def test_single_and_multi_and_all_can_share_one_batch():
    entries = [{"track_index": 0}, {"track_indices": [2, 3]}, {"all": True}]
    assert len(_normalize_track_delete_entries(entries)) == 3


@pytest.mark.parametrize("entries", [
    [],
    {},
    "x",
    None,
    ["not a dict"],
    [{}],                                              # no selector
    [{"all": True, "track_index": 1}],                 # two selectors
    [{"all": False}],
    [{"track_index": -1}],                             # the master track
    [{"track_index": -2}],
    [{"track_index": True}],
    [{"track_index": "1"}],
    [{"track_index": 1.5}],
    [{"track_indices": []}],
    [{"track_indices": [0, -1]}],
    [{"track_indices": [0, "1"]}],
    [{"track_indices": "0,1"}],
])
def test_malformed_entries_are_refused(entries):
    with pytest.raises(ReaperMCPError):
        _normalize_track_delete_entries(entries)


def test_the_master_track_is_named_in_the_refusal():
    with pytest.raises(ReaperMCPError) as raised:
        _normalize_track_delete_entries([{"track_index": -1}])
    assert "master" in str(raised.value).lower()


def test_entry_count_is_capped():
    with pytest.raises(ReaperMCPError) as raised:
        _normalize_track_delete_entries([{"track_index": 0}] * 201)
    assert raised.value.code == ErrorCode.VALUE_OUT_OF_RANGE


def test_the_error_names_the_offending_entry():
    with pytest.raises(ReaperMCPError) as raised:
        _normalize_track_delete_entries([{"track_index": 0}, {"track_index": "x"}])
    assert "Entry 1" in str(raised.value)


# ---- the single tool is gone ----------------------------------------------

def test_single_track_delete_is_gone_everywhere():
    for path in (ROOT / "reaper_mcp").rglob("*.py"):
        assert '"track_delete"' not in path.read_text(encoding="utf-8"), path
    lua = LUA.read_text(encoding="utf-8")
    assert "function track.track_delete(" not in lua
    assert "function track.track_delete_batch(p)" in lua


# ---- Lua handler, run for real under lupa with tracks that shift ----------

def _load_handler(lupa, names):
    source = LUA.read_text(encoding="utf-8")
    helpers = source[
        source.index("local MASTER_TRACK_INDEX = -1"):
        source.index("local function batch_track_from_index")
    ]
    start = source.index("function track.track_delete_batch(p)")
    handler = source[start: source.index("\nend\n", start) + len("\nend\n")]

    runtime = lupa.LuaRuntime()
    quoted = ", ".join(f'{{name = "{n}"}}' for n in names)
    runtime.execute(
        f"""
        tracks = {{ {quoted} }}
        MASTER = {{name = "MASTER"}}
        deleted_order = {{}}
        reaper = {{
          CountTracks = function(_) return #tracks end,
          GetTrack = function(_, i) return tracks[i + 1] end,
          GetMasterTrack = function(_) return MASTER end,
          GetTrackName = function(tr) return true, tr.name end,
          DeleteTrack = function(tr)
            for i, t in ipairs(tracks) do
              if t == tr then table.remove(tracks, i); break end
            end
            deleted_order[#deleted_order + 1] = tr.name
          end,
          Undo_BeginBlock = function() end,
          Undo_EndBlock = function() end,
          UpdateArrange = function() end,
        }}
        track = {{}}
        """
    )
    runtime.execute(helpers + handler + "\nrun = track.track_delete_batch")
    run = runtime.eval("run")

    def call(entries):
        params = runtime.table_from({"entries": entries}, recursive=True)
        return run(params)

    def remaining():
        return [t["name"] for t in runtime.eval("tracks").values()]

    def order():
        return list(runtime.eval("deleted_order").values())

    return call, remaining, order


def test_deletes_a_single_track():
    lupa = pytest.importorskip("lupa")
    call, remaining, _ = _load_handler(lupa, ["A", "B", "C", "D"])
    result = call([{"track_index": 1}])
    assert remaining() == ["A", "C", "D"]
    assert result["deleted"] == 1 and result["remaining_tracks"] == 3


def test_deletes_several_and_ignores_a_duplicate_across_entries():
    lupa = pytest.importorskip("lupa")
    call, remaining, _ = _load_handler(lupa, ["A", "B", "C", "D"])
    result = call([{"track_indices": [0, 2]}, {"track_index": 2}])
    assert remaining() == ["B", "D"]
    assert result["deleted"] == 2


def test_all_clears_every_track():
    lupa = pytest.importorskip("lupa")
    call, remaining, _ = _load_handler(lupa, ["A", "B", "C"])
    result = call([{"all": True}])
    assert remaining() == []
    assert result["deleted"] == 3 and result["remaining_tracks"] == 0


def test_outcome_does_not_depend_on_entry_order():
    lupa = pytest.importorskip("lupa")
    for entries in ([{"track_index": 3}, {"track_index": 0}],
                    [{"track_index": 0}, {"track_index": 3}]):
        call, remaining, _ = _load_handler(lupa, ["A", "B", "C", "D"])
        call(entries)
        assert remaining() == ["B", "C"]


def test_tracks_are_deleted_highest_index_first():
    lupa = pytest.importorskip("lupa")
    call, _, order = _load_handler(lupa, ["A", "B", "C", "D"])
    call([{"track_indices": [0, 1, 3]}])
    assert order() == ["D", "B", "A"]


def test_the_result_lists_what_was_deleted_by_original_index():
    lupa = pytest.importorskip("lupa")
    call, _, _ = _load_handler(lupa, ["A", "B", "C", "D"])
    result = call([{"track_indices": [3, 1]}])
    listed = [(t["track_index"], t["name"]) for t in result["deleted_tracks"].values()]
    assert listed == [(1, "B"), (3, "D")]


def test_bad_entries_are_reported_and_do_not_abort_the_rest():
    lupa = pytest.importorskip("lupa")
    call, remaining, _ = _load_handler(lupa, ["A", "B", "C"])
    result = call([
        {"track_index": 9},          # no such track
        {"track_index": -1},         # master: never deletable
        {},                          # no selector
        {"track_index": 0},          # fine
    ])
    assert remaining() == ["B", "C"]
    assert result["deleted"] == 1
    messages = " | ".join(e["error"] for e in result["errors"].values())
    assert "not found" in messages.lower()
    assert "master" in messages.lower()
    assert "needs one of" in messages.lower()
    assert len(result["errors"]) == 3


def test_the_master_track_survives_even_if_asked_by_name_all_or_index():
    lupa = pytest.importorskip("lupa")
    call, remaining, order = _load_handler(lupa, ["A"])
    call([{"track_index": -1}, {"all": True}])
    assert "MASTER" not in order()
    assert remaining() == []


# ---- mix engine: reverb-bus cleanup is one batch call ---------------------

class _FakeClient:
    def __init__(self, track_names):
        self.tracks = [{"index": i, "name": n} for i, n in enumerate(track_names)]
        self.calls = []

    async def execute(self, command, **params):
        self.calls.append((command, params))
        if command == "track_get_all":
            return {"data": {"tracks": self.tracks}}
        if command == "fx_get_chain":
            return {"data": {"fx_chain": []}}
        return {"data": {}}


@pytest.mark.asyncio
async def test_cleanup_deletes_all_reverb_buses_in_one_batch_call():
    names = ["kick", "bass", f"{_REVERB_BUS_PREFIX}Hall", f"{_REVERB_BUS_PREFIX}Room", "user bus"]
    client = _FakeClient(names)
    await _clean_mix_fx_generic(client, [])

    deletions = [c for c in client.calls if c[0] == "track_delete_batch"]
    assert len(deletions) == 1
    entries = json.loads(deletions[0][1]["entries"])
    assert entries == [{"track_indices": [3, 2]}]
    assert not any(c[0] == "track_delete" for c in client.calls)


@pytest.mark.asyncio
async def test_cleanup_makes_no_delete_call_when_there_are_no_buses():
    client = _FakeClient(["kick", "bass"])
    await _clean_mix_fx_generic(client, [])
    assert not any(c[0] == "track_delete_batch" for c in client.calls)
