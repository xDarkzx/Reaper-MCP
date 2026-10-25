"""Handlers run the REAPER actions they claim to.

Every ID below was checked against REAPER 7.x's own action names via
kbd_getTextFromCmd. Before this fix:
- project_set_ripple_mode was off by one: mode 0 set per-track ripple,
  mode 1 all-tracks, and mode 2 ran 40312 "Item: Remove selected area of
  items". It also called GetSetRepeatEx(0, 0), turning loop-repeat off.
- item_split_at_transients ran 40310 ("Set ripple editing per-track"), so it
  switched ripple on and never split. REAPER has no split-at-transients
  main action.
- take_set_reversed ran 41051 ("Toggle take reverse") instead of 40270
  ("Reverse items to new take"), so a second call un-reversed the item.
"""

from pathlib import Path

import pytest

LUA_SRC = Path(__file__).resolve().parent.parent / "reaper_scripts" / "reaper_mcp_server.lua"


def _handler(rt, signature):
    source = LUA_SRC.read_text(encoding="utf-8")
    start = source.index(signature)
    end = source.index("\nend\n", start)
    rt.execute(source[start:end] + "\nend\n")


def _runtime(stub):
    lupa = pytest.importorskip("lupa")
    rt = lupa.LuaRuntime()
    rt.execute(stub)
    return rt


RIPPLE_STUB = """
project = {}
calls = {}
repeat_touched = false
reaper = {
  Main_OnCommand = function(cmd) calls[#calls+1] = cmd end,
  GetSetRepeatEx = function() repeat_touched = true end,
}
"""


@pytest.mark.parametrize("mode,cmd", [(0, 40309), (1, 40310), (2, 40311)])
def test_ripple_mode_runs_verified_action(mode, cmd):
    rt = _runtime(RIPPLE_STUB)
    _handler(rt, "function project.project_set_ripple_mode(p)")
    rt.eval("project.project_set_ripple_mode")(rt.table_from({"mode": mode}))
    assert list(rt.eval("calls").values()) == [cmd]


def test_ripple_mode_does_not_touch_loop_repeat():
    rt = _runtime(RIPPLE_STUB)
    _handler(rt, "function project.project_set_ripple_mode(p)")
    rt.eval("project.project_set_ripple_mode")(rt.table_from({"mode": 0}))
    assert rt.eval("repeat_touched") is False


def test_take_set_reversed_reverses_to_new_take():
    rt = _runtime("""
    item = {}
    calls = {}
    reaper = {
      GetMediaItem = function() return "IT" end,
      Undo_BeginBlock = function() end, Undo_EndBlock = function() end,
      PreventUIRefresh = function() end, UpdateArrange = function() end,
      SetMediaItemSelected = function() end,
      Main_OnCommand = function(cmd) calls[#calls+1] = cmd end,
    }
    """)
    _handler(rt, "function item.take_set_reversed(p)")
    rt.eval("item.take_set_reversed")(rt.table_from({"item_index": 0}))
    calls = list(rt.eval("calls").values())
    assert 40270 in calls
    assert 41051 not in calls


SPLIT_STUB = """
item = {}
calls = {}
splits = {}
cursor = 7.5
transients = {1.5, 2.25, 3.0}  -- item spans 1.0 .. 4.0
items = {"IT"}
reaper = {
  GetMediaItem = function(proj, i) return items[i + 1] end,
  GetMediaItem_Track = function() return "TR" end,
  GetMediaItemInfo_Value = function(it, key)
    if key == "D_POSITION" then return 1.0 end
    return 3.0
  end,
  Undo_BeginBlock = function() end, Undo_EndBlock = function() end,
  PreventUIRefresh = function() end, UpdateArrange = function() end,
  SetMediaItemSelected = function() end,
  CountMediaItems = function() return #items end,
  GetCursorPosition = function() return cursor end,
  SetEditCurPos = function(t) cursor = t end,
  Main_OnCommand = function(cmd)
    calls[#calls+1] = cmd
    if cmd == 40375 then
      for _, t in ipairs(transients) do
        if t > cursor + 1e-9 then cursor = t; return end
      end
    end
  end,
  SplitMediaItem = function(it, pos)
    splits[#splits+1] = pos
    items[#items+1] = "R" .. #items
    return items[#items]
  end,
  CountTrackMediaItems = function() return 0 end,
  GetTrackMediaItem = function() return nil end,
}
"""


def test_split_at_transients_splits_at_each_transient_right_to_left():
    rt = _runtime(SPLIT_STUB)
    _handler(rt, "function item.item_split_at_transients(p)")
    result = rt.eval("item.item_split_at_transients")(rt.table_from({"item_index": 0}))
    assert list(rt.eval("splits").values()) == [3.0, 2.25, 1.5]
    assert result["chops_created"] == 3


def test_split_at_transients_never_runs_ripple_action_and_restores_cursor():
    rt = _runtime(SPLIT_STUB)
    _handler(rt, "function item.item_split_at_transients(p)")
    rt.eval("item.item_split_at_transients")(rt.table_from({"item_index": 0}))
    assert 40310 not in list(rt.eval("calls").values())
    assert rt.eval("cursor") == 7.5
