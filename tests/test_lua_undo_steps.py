"""Undo by count, and undo a whole multi-command tool run.

A tool that runs 10 commands leaves 10 undo steps, each labelled
"MCP: <tool>#<run> > <command>". You can undo the last 2 or 3 of them with
project_undo(steps=N), or the whole run with project_undo_group. Nothing is
held open in REAPER, so every step stays individually undoable.
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


def _load(lupa, undo_stack, redo_stack=()):
    """Run the real undo/redo handlers against a simulated REAPER undo history."""
    source = _source()
    start = source.index("local MAX_UNDO_STEPS")
    tail = source.index("function project.project_undo_group(p)")
    end = source.index("\nend\n", tail) + len("\nend\n")

    runtime = lupa.LuaRuntime()
    stack = ", ".join(f'"{s}"' for s in undo_stack)
    redo = ", ".join(f'"{s}"' for s in redo_stack)
    runtime.execute(
        f"""
        stack = {{ {stack} }}
        redo = {{ {redo} }}
        project = {{}}
        reaper = {{
          Undo_CanUndo2 = function() return stack[#stack] end,
          Undo_CanRedo2 = function() return redo[#redo] end,
          Main_OnCommand = function(cmd)
            if cmd == 40029 then
              local n = table.remove(stack); if n then redo[#redo + 1] = n end
            elseif cmd == 40030 then
              local n = table.remove(redo); if n then stack[#stack + 1] = n end
            end
          end,
        }}
        """
    )
    runtime.execute(source[start:end])

    def call(name, **params):
        handler = runtime.eval(f"project.{name}")
        return handler(runtime.table_from(params))

    def history():
        return [list(runtime.eval("stack").values()), list(runtime.eval("redo").values())]

    def names(table):
        return list(table.values())

    return call, history, names


# ---- undo by count --------------------------------------------------------

def test_a_plain_undo_still_undoes_one_step():
    lupa = pytest.importorskip("lupa")
    call, history, _ = _load(lupa, ["a", "b", "c"])
    result = call("project_undo")
    assert result["undone"] == "c" and result["steps_undone"] == 1
    assert result["next_undo"] == "b" and result["next_redo"] == "c"
    assert history()[0] == ["a", "b"]


def test_undo_by_count_undoes_that_many_most_recent_first():
    lupa = pytest.importorskip("lupa")
    call, history, names = _load(lupa, ["a", "b", "c", "d", "e"])
    result = call("project_undo", steps=3)
    assert names(result["undone_steps"]) == ["e", "d", "c"]
    assert result["steps_undone"] == 3 and result["undone"] == "e"
    assert history()[0] == ["a", "b"]


def test_undo_by_count_stops_when_the_history_runs_out():
    lupa = pytest.importorskip("lupa")
    call, history, names = _load(lupa, ["a", "b"])
    result = call("project_undo", steps=10)
    assert names(result["undone_steps"]) == ["b", "a"]
    assert result["steps_undone"] == 2 and result["next_undo"] == ""


def test_undo_with_an_empty_history_undoes_nothing():
    lupa = pytest.importorskip("lupa")
    call, _, _ = _load(lupa, [])
    result = call("project_undo")
    assert result["steps_undone"] == 0 and result["undone"] == ""


@pytest.mark.parametrize("steps", [0, -1, 101, 1000])
def test_the_step_count_is_bounded(steps):
    lupa = pytest.importorskip("lupa")
    call, history, _ = _load(lupa, ["a", "b"])
    result, err = call("project_undo", steps=steps)
    assert result is None and "between 1 and" in err
    assert history()[0] == ["a", "b"]           # nothing was undone


def test_redo_by_count_replays_that_many_steps():
    lupa = pytest.importorskip("lupa")
    call, history, names = _load(lupa, ["a"], redo_stack=["d", "c", "b"])
    result = call("project_redo", steps=2)
    assert names(result["redone_steps"]) == ["b", "c"]
    assert history() == [["a", "b", "c"], ["d"]]


def test_redo_step_count_is_bounded_too():
    lupa = pytest.importorskip("lupa")
    call, _, _ = _load(lupa, [], redo_stack=["a"])
    result, err = call("project_redo", steps=0)
    assert result is None and "between 1 and" in err


# ---- undo a whole tool run ------------------------------------------------

def test_undo_group_undoes_every_step_of_the_last_run_and_stops_there():
    lupa = pytest.importorskip("lupa")
    call, history, names = _load(lupa, [
        "MCP: track_set_volume",
        "MCP: engine_mix#7 > setup_fx_chain",
        "MCP: engine_mix#7 > configure_tracks",
        "MCP: engine_mix#7 > setup_sidechain",
    ])
    result = call("project_undo_group")
    assert result["group"] == "engine_mix" and result["steps_undone"] == 3
    assert names(result["undone_steps"])[0] == "MCP: engine_mix#7 > setup_sidechain"
    assert history()[0] == ["MCP: track_set_volume"]


def test_undo_group_does_not_cross_into_an_earlier_run_of_the_same_tool():
    lupa = pytest.importorskip("lupa")
    call, history, _ = _load(lupa, [
        "MCP: engine_mix#6 > setup_fx_chain",
        "MCP: engine_mix#7 > setup_fx_chain",
        "MCP: engine_mix#7 > configure_tracks",
    ])
    result = call("project_undo_group")
    assert result["steps_undone"] == 2
    assert history()[0] == ["MCP: engine_mix#6 > setup_fx_chain"]


def test_undo_group_refuses_when_the_last_step_is_not_part_of_a_run():
    lupa = pytest.importorskip("lupa")
    call, history, _ = _load(lupa, ["MCP: engine_mix#7 > a", "MCP: track_set_volume"])
    result, err = call("project_undo_group")
    assert result is None and "project_undo" in err
    assert len(history()[0]) == 2               # nothing was undone


def test_undo_group_with_an_empty_history_refuses():
    lupa = pytest.importorskip("lupa")
    call, _, _ = _load(lupa, [])
    result, err = call("project_undo_group")
    assert result is None and err


# ---- wired in -------------------------------------------------------------

def test_undo_and_redo_stay_exempt_from_recording_a_step_of_their_own():
    source = _source()
    start = source.index("local UNDO_EXEMPT_COMMANDS = {")
    exempt = source[start: source.index("\n}\n", start)]
    for name in ("project_undo", "project_redo", "project_undo_group"):
        assert f"{name} =" in exempt
