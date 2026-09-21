"""Undo groups label a tool's steps; they never hold an undo block open.

`undo_group_begin` starts labelling. While it is open, every undo step made
is named "MCP: <tool>#<run> > <command>", so the steps of one multi-command
tool run can be told apart and undone by count or as a whole. REAPER drops an
undo block that is held open between bridge ticks, so the group holds nothing
open: each command still records its own step.
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
    end = source.index("local unwind_open_blocks")
    runtime = lupa.LuaRuntime()
    runtime.execute(
        """
        calls = {}
        reaper = {
          PreventUIRefresh = function(n) calls[#calls+1] = "ui:" .. n end,
          Undo_BeginBlock  = function() calls[#calls+1] = "begin" end,
          Undo_EndBlock    = function(d, f) calls[#calls+1] = "end:" .. tostring(d) .. ":" .. tostring(f) end,
        }
        """
    )
    runtime.execute(source[start:end] + "\nunwind, group = install_block_guard(reaper)")

    def run(code):
        return runtime.execute(code)

    def calls():
        return list(runtime.eval("calls").values())

    return run, calls


# ---- labelling ------------------------------------------------------------

def test_steps_made_inside_a_group_carry_the_tool_and_run_number():
    lupa = pytest.importorskip("lupa")
    run, calls = _load(lupa)
    run("group.begin('engine_mix', 0)")
    run("reaper.Undo_BeginBlock(); reaper.Undo_EndBlock('MCP: setup_fx_chain', -1)")
    assert calls() == ["begin", "end:MCP: engine_mix#1 > setup_fx_chain:-1"]


def test_a_step_named_without_the_mcp_prefix_is_labelled_the_same_way():
    """Some handlers name their block plainly, e.g. 'setup_fx_chain'."""
    lupa = pytest.importorskip("lupa")
    run, calls = _load(lupa)
    run("group.begin('engine_mix', 0)")
    run("reaper.Undo_BeginBlock(); reaper.Undo_EndBlock('setup_fx_chain', -1)")
    assert calls()[-1] == "end:MCP: engine_mix#1 > setup_fx_chain:-1"


def test_steps_outside_a_group_keep_their_own_name():
    lupa = pytest.importorskip("lupa")
    run, calls = _load(lupa)
    run("reaper.Undo_BeginBlock(); reaper.Undo_EndBlock('MCP: track_set_volume', -1)")
    assert calls()[-1] == "end:MCP: track_set_volume:-1"


def test_the_recorder_label_matches_the_block_label():
    lupa = pytest.importorskip("lupa")
    run, _ = _load(lupa)
    run("group.begin('engine_mix', 0)")
    assert run("return group.label('MCP: track_set_volume')") == "MCP: engine_mix#1 > track_set_volume"


def test_a_step_the_unwinder_had_to_close_is_labelled_too():
    lupa = pytest.importorskip("lupa")
    run, calls = _load(lupa)
    run("group.begin('engine_mix', 0); reaper.Undo_BeginBlock()")
    run("unwind()")
    assert "MCP: engine_mix#1 > aborted" in calls()[-1]


# ---- nothing is held open -------------------------------------------------

def test_a_group_holds_no_undo_block_open():
    lupa = pytest.importorskip("lupa")
    run, calls = _load(lupa)
    run("group.begin('engine_mix', 0)")
    run("group.finish()")
    assert calls() == []


def test_each_command_in_a_group_still_commits_its_own_step():
    lupa = pytest.importorskip("lupa")
    run, calls = _load(lupa)
    run("group.begin('x', 0)")
    run("reaper.Undo_BeginBlock(); reaper.Undo_EndBlock('a', -1)")
    run("reaper.Undo_BeginBlock(); reaper.Undo_EndBlock('b', -1)")
    assert sum(c.startswith("end:") for c in calls()) == 2
    assert run("return unwind().committed") is True


def test_unwinding_inside_a_group_still_closes_a_leaked_block():
    lupa = pytest.importorskip("lupa")
    run, calls = _load(lupa)
    run("group.begin('x', 0); reaper.Undo_BeginBlock(); reaper.PreventUIRefresh(1)")
    unwound = run("return unwind()")
    assert unwound["undo"] == 1 and unwound["ui"] == 1


# ---- run numbers and nesting ---------------------------------------------

def test_begin_returns_the_run_number_and_each_run_gets_the_next_one():
    lupa = pytest.importorskip("lupa")
    run, _ = _load(lupa)
    assert run("return group.begin('a', 0)") == 1
    run("group.finish()")
    assert run("return group.begin('b', 0)") == 2


def test_a_nested_group_joins_the_outer_run():
    lupa = pytest.importorskip("lupa")
    run, calls = _load(lupa)
    assert run("return group.begin('outer', 0)") == 1
    assert run("return group.begin('inner', 1)") == 1          # same run
    run("reaper.Undo_BeginBlock(); reaper.Undo_EndBlock('a', -1)")
    assert calls()[-1] == "end:MCP: outer#1 > a:-1"
    assert run("return group.finish()") is False               # outer still open
    assert run("return group.is_open()") is True
    assert run("return group.finish()") is True
    assert run("return group.is_open()") is False


def test_finishing_a_group_that_is_not_open_is_harmless():
    lupa = pytest.importorskip("lupa")
    run, calls = _load(lupa)
    assert run("return group.finish()") is False
    assert calls() == []


# ---- failsafe -------------------------------------------------------------

def test_an_abandoned_group_stops_labelling_after_the_idle_limit():
    lupa = pytest.importorskip("lupa")
    run, _ = _load(lupa)
    run("group.begin('engine_mix', 100)")
    assert run("return group.expire(150, 60)") is None
    assert run("return group.expire(161, 60)") == "engine_mix"
    assert run("return group.is_open()") is False
    assert run("return group.label('MCP: solo')") == "MCP: solo"


def test_activity_keeps_a_group_alive():
    lupa = pytest.importorskip("lupa")
    run, _ = _load(lupa)
    run("group.begin('x', 0)")
    run("group.touch(55)")
    assert run("return group.expire(100, 60)") is None


def test_expiry_does_nothing_when_no_group_is_open():
    lupa = pytest.importorskip("lupa")
    run, _ = _load(lupa)
    assert run("return group.expire(1e9, 60)") is None


# ---- wired into the bridge ------------------------------------------------

def test_the_group_commands_exist_and_are_exempt_from_recording():
    source = _source()
    assert "function undo_group_commands.undo_group_begin(p)" in source
    assert "function undo_group_commands.undo_group_end(p)" in source
    assert "for name, handler in pairs(undo_group_commands)" in source
    start = source.index("local UNDO_EXEMPT_COMMANDS = {")
    exempt = source[start: source.index("\n}\n", start)]
    assert "undo_group_begin =" in exempt and "undo_group_end =" in exempt


def test_the_dispatcher_labels_the_step_it_records_and_keeps_the_group_alive():
    source = _source()
    dispatch = source[source.index("local function process_command"):]
    dispatch = dispatch[: dispatch.index("local function main_loop")]
    assert "undo_group.touch(" in dispatch
    assert "undo_group.label(step_name)" in dispatch
    assert "is_open()" not in dispatch      # no skipping: every command keeps its step


def test_the_main_loop_expires_an_abandoned_group():
    source = _source()
    loop = source[source.index("local function main_loop"):]
    loop = loop[: loop.index("\nend\n")]
    assert "undo_group.expire(" in loop
    assert "UNDO_GROUP_IDLE_SECONDS" in source
