"""Destructive track handlers refuse the master track in Lua itself.

`get_track` maps track_index -1 to the master track, and ~40 handlers use
it. Which of them are reachable with -1 is decided today only by the Python
guards in front of them. Handlers that delete, freeze, re-route, re-arm or
overwrite the state of a track have no sensible meaning on the master, so
they use `get_numbered_track`, which keeps refusing -1 even if a Python
guard is later loosened (or the handler is reached some other way).
"""

import re
from pathlib import Path

import pytest

LUA_SRC = (
    Path(__file__).resolve().parent.parent
    / "reaper_scripts"
    / "reaper_mcp_server.lua"
)

# Handlers where "the master track" is meaningless or dangerous.
DESTRUCTIVE_HANDLERS = [
    "track_freeze",
    "track_unfreeze",
    "track_set_folder",
    "track_set_input",
    "track_set_record_arm",
    "track_set_state_chunk",
]


def _source() -> str:
    return LUA_SRC.read_text(encoding="utf-8")


def _handler_head(name: str) -> str:
    source = _source()
    start = source.index(f"function track.{name}(p)")
    return source[start: start + 200]


@pytest.mark.parametrize("name", DESTRUCTIVE_HANDLERS)
def test_destructive_handler_uses_the_numbered_track_guard(name):
    head = _handler_head(name)
    assert "get_numbered_track(p)" in head, name
    assert "get_track(p)" not in head, name


def test_track_delete_batch_resolves_every_target_through_the_guard():
    source = _source()
    start = source.index("function track.track_delete_batch(p)")
    body = source[start: source.index("\nend\n", start)]
    assert "get_numbered_track(" in body
    assert "get_track(" not in body.replace("get_numbered_track(", "")


def test_read_only_and_mixer_handlers_still_resolve_the_master():
    for name in ("track_get_info", "track_get_state_chunk", "track_set_volume"):
        assert "get_track(p)" in _handler_head(name), name


def _load_helpers(lupa):
    """Run the real get_track / get_numbered_track under a stubbed `reaper`."""
    source = _source()
    start = source.index("local MASTER_TRACK_INDEX = -1")
    end = source.index("local function batch_track_from_index")
    runtime = lupa.LuaRuntime()
    runtime.execute(
        """
        reaper = {
          GetMasterTrack = function(_) return "MASTER" end,
          GetTrack = function(_, i) if i < 3 then return "TRACK" .. i end end,
        }
        """
    )
    get_track, get_numbered_track = runtime.execute(
        source[start:end] + "\nreturn get_track, get_numbered_track"
    )

    # Handlers receive Lua tables (a missing key is nil); a plain Python dict
    # would raise KeyError instead, so convert before calling.
    def as_call(fn):
        return lambda params: fn(runtime.table_from(params))

    return as_call(get_track), as_call(get_numbered_track)


def test_get_track_still_resolves_the_master():
    lupa = pytest.importorskip("lupa")
    get_track, _ = _load_helpers(lupa)
    tr, idx, err = get_track({"track_index": -1})
    assert (tr, idx, err) == ("MASTER", -1, None)


def test_get_numbered_track_refuses_the_master():
    lupa = pytest.importorskip("lupa")
    _, get_numbered_track = _load_helpers(lupa)
    tr, idx, err = get_numbered_track({"track_index": -1})
    assert tr is None and idx is None
    assert "master" in err.lower()


def test_get_numbered_track_resolves_normal_tracks_and_reports_misses():
    lupa = pytest.importorskip("lupa")
    _, get_numbered_track = _load_helpers(lupa)
    assert get_numbered_track({"track_index": 2}) == ("TRACK2", 2, None)
    tr, _, err = get_numbered_track({"track_index": 9})
    assert tr is None and "not found" in err.lower()
    tr, _, err = get_numbered_track({})
    assert tr is None and "missing" in err.lower()


def test_the_guard_helper_is_defined_once_next_to_get_track():
    source = _source()
    assert len(re.findall(r"local function get_numbered_track\(", source)) == 1
    assert source.index("local function get_track(") < source.index(
        "local function get_numbered_track("
    ) < source.index("local function batch_track_from_index")
