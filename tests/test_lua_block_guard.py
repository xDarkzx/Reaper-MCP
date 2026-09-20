"""A command that throws mid-way cannot leave REAPER's UI frozen or an undo block open.

Handlers open `PreventUIRefresh(1)` and undo blocks and close them on their
last lines. If one throws in between - a malformed entry is enough - the
dispatcher's pcall catches the error, but the closing calls never run, so
REAPER would stay frozen with an undo block open. The dispatcher instead
tracks every open/close through a small wrapper around the reaper API and
unwinds whatever a command left unbalanced, however it exited.
"""

from pathlib import Path

import pytest

LUA_SRC = (
    Path(__file__).resolve().parent.parent
    / "reaper_scripts"
    / "reaper_mcp_server.lua"
)


def _source() -> str:
    return LUA_SRC.read_text(encoding="utf-8")


def _load(lupa):
    """Run the real install_block_guard against a recording stub of the API."""
    source = _source()
    start = source.index("local function install_block_guard")
    end = source.index("local unwind_open_blocks = install_block_guard(reaper)")
    runtime = lupa.LuaRuntime()
    runtime.execute(
        """
        calls = {}
        reaper = {
          PreventUIRefresh = function(n) calls[#calls+1] = "ui:" .. n end,
          Undo_BeginBlock  = function() calls[#calls+1] = "begin" end,
          Undo_EndBlock    = function(d, f) calls[#calls+1] = "end:" .. tostring(d) .. ":" .. tostring(f); return 7 end,
        }
        """
    )
    runtime.execute(
        source[start:end]
        + "\nunwind = install_block_guard(reaper)"
    )
    return runtime


def _calls(runtime):
    return list(runtime.eval("calls").values())


def test_balanced_use_is_left_alone():
    lupa = pytest.importorskip("lupa")
    lua = _load(lupa)
    lua.execute(
        "reaper.Undo_BeginBlock(); reaper.PreventUIRefresh(1);"
        " reaper.PreventUIRefresh(-1); reaper.Undo_EndBlock('x', -1)"
    )
    before = _calls(lua)
    unwound = lua.eval("unwind()")
    assert (unwound["ui"], unwound["undo"]) == (0, 0)
    assert _calls(lua) == before == ["begin", "ui:1", "ui:-1", "end:x:-1"]


def test_a_throw_between_open_and_close_is_unwound():
    lupa = pytest.importorskip("lupa")
    lua = _load(lupa)
    lua.execute(
        """
        pcall(function()
          reaper.Undo_BeginBlock()
          reaper.PreventUIRefresh(1)
          error("malformed entry")
        end)
        """
    )
    unwound = lua.eval("unwind()")
    assert (unwound["ui"], unwound["undo"]) == (1, 1)
    calls = _calls(lua)
    assert "ui:-1" in calls
    assert any(c.startswith("end:") and "-1" in c for c in calls)


def test_nested_refresh_holds_are_released_in_one_call():
    lupa = pytest.importorskip("lupa")
    lua = _load(lupa)
    lua.execute("reaper.PreventUIRefresh(1); reaper.PreventUIRefresh(1)")
    assert lua.eval("unwind()")["ui"] == 2
    assert _calls(lua)[-1] == "ui:-2"


def test_state_resets_so_the_next_command_starts_clean():
    lupa = pytest.importorskip("lupa")
    lua = _load(lupa)
    lua.execute("reaper.Undo_BeginBlock(); reaper.PreventUIRefresh(1)")
    lua.eval("unwind()")
    recorded = len(_calls(lua))
    unwound = lua.eval("unwind()")
    assert (unwound["ui"], unwound["undo"]) == (0, 0)
    assert len(_calls(lua)) == recorded


def test_an_extra_end_block_never_drives_the_count_negative():
    """Handlers close early on error paths, so EndBlock can outnumber BeginBlock."""
    lupa = pytest.importorskip("lupa")
    lua = _load(lupa)
    lua.execute("reaper.Undo_EndBlock('early', -1); reaper.Undo_BeginBlock()")
    assert lua.eval("unwind()")["undo"] == 1


def test_the_wrapped_api_still_passes_arguments_and_return_values_through():
    lupa = pytest.importorskip("lupa")
    lua = _load(lupa)
    assert lua.eval("reaper.Undo_EndBlock('desc', 4)") == 7
    assert _calls(lua) == ["end:desc:4"]


def test_the_dispatcher_unwinds_after_every_command():
    source = _source()
    dispatch = source[source.index("local function process_command"):]
    dispatch = dispatch[: dispatch.index("local function main_loop")]
    assert dispatch.index("pcall(handler") < dispatch.index("unwind_open_blocks()")
    # ...and before any response is written, so it covers success and failure.
    assert dispatch.index("unwind_open_blocks()") < dispatch.index("send_success(result")
    assert dispatch.index("unwind_open_blocks()") < dispatch.index("send_error(err, req_id)")


def test_the_guard_is_installed_once_before_any_command_runs():
    source = _source()
    assert source.count("install_block_guard(reaper)") == 1
    assert source.index("install_block_guard(reaper)") < source.index("local function process_command")
