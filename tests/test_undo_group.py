"""Python side of undo groups: the context manager, the tool decorator, and
the undo tools that take a step count."""

import inspect
import re
from pathlib import Path

import pytest

from reaper_mcp.tools.project_tools import _MAX_UNDO_STEPS, _check_undo_steps
from reaper_mcp.undo_group import undo_group, undo_grouped
from reaper_mcp_shared.error_codes import ErrorCode, ReaperMCPError

ROOT = Path(__file__).resolve().parent.parent


class _FakeClient:
    def __init__(self, fail_begin=False, fail_end=False):
        self.calls = []
        self.fail_begin = fail_begin
        self.fail_end = fail_end

    async def execute(self, command, **params):
        self.calls.append((command, params))
        if command == "undo_group_begin" and self.fail_begin:
            raise RuntimeError("Unknown command: undo_group_begin")
        if command == "undo_group_end" and self.fail_end:
            raise RuntimeError("bridge went away")
        return {"data": {}}

    def names(self):
        return [c[0] for c in self.calls]


# ---- context manager ------------------------------------------------------

@pytest.mark.asyncio
async def test_the_group_wraps_the_body_in_begin_and_end():
    client = _FakeClient()
    async with undo_group(client, "engine_mix"):
        await client.execute("setup_fx_chain")
        await client.execute("configure_tracks")
    assert client.names() == [
        "undo_group_begin", "setup_fx_chain", "configure_tracks", "undo_group_end",
    ]
    assert client.calls[0][1] == {"name": "engine_mix"}


@pytest.mark.asyncio
async def test_the_group_is_closed_even_when_the_body_raises():
    client = _FakeClient()
    with pytest.raises(ValueError):
        async with undo_group(client, "x"):
            raise ValueError("boom")
    assert client.names() == ["undo_group_begin", "undo_group_end"]


@pytest.mark.asyncio
async def test_an_older_bridge_without_the_command_just_runs_ungrouped():
    """Version skew: begin fails, so the body still runs and no end is sent."""
    client = _FakeClient(fail_begin=True)
    async with undo_group(client, "x"):
        await client.execute("setup_fx_chain")
    assert client.names() == ["undo_group_begin", "setup_fx_chain"]


@pytest.mark.asyncio
async def test_a_failure_closing_the_group_never_masks_the_result():
    client = _FakeClient(fail_end=True)
    async with undo_group(client, "x"):
        pass    # must not raise


# ---- decorator ------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_decorator_groups_the_call_and_returns_its_result():
    client = _FakeClient()

    @undo_grouped(client, "my_tool")
    async def my_tool(style: str, clean: bool = True) -> dict:
        """My docstring."""
        await client.execute("setup_fx_chain")
        return {"style": style}

    assert await my_tool("house") == {"style": "house"}
    assert client.names() == ["undo_group_begin", "setup_fx_chain", "undo_group_end"]


def test_the_decorator_preserves_the_signature_and_docstring():
    """FastMCP builds each tool's schema from these, so they must survive."""
    client = _FakeClient()

    @undo_grouped(client, "my_tool")
    async def my_tool(style: str, clean: bool = True) -> dict:
        """My docstring."""

    assert my_tool.__name__ == "my_tool"
    assert my_tool.__doc__ == "My docstring."
    params = inspect.signature(my_tool).parameters
    assert list(params) == ["style", "clean"]
    assert params["clean"].default is True


# ---- the tools that run several commands are grouped ----------------------

GROUPED_TOOLS = {
    "mix_tools.py": ["engine_fix_mix", "engine_master", "engine_mix"],
    "pipeline_tools.py": ["setup_vocal_chain", "setup_drum_bus", "setup_parallel_compression"],
    "chops_tools.py": ["chop_pipeline", "stack_chop_layers"],
    "compose_tools.py": ["compose_arrangement"],
    "demo_tools.py": ["demo_edm_project"],
    "loops_tools.py": ["load_loops"],
    "sidechain_tools.py": ["setup_sidechain"],
    "patterns_tools.py": ["create_drum_pattern", "create_chord_progression"],
    "compose_edit_tools.py": ["wipe_all_midi"],
}


@pytest.mark.parametrize(
    "filename,tool",
    [(f, t) for f, tools in GROUPED_TOOLS.items() for t in tools],
)
def test_multi_command_tools_are_undo_grouped(filename, tool):
    source = (ROOT / "reaper_mcp" / "tools" / filename).read_text(encoding="utf-8")
    match = re.search(rf"((?:    @.*\n)+)    async def {tool}\(", source)
    assert match, f"{tool} not found in {filename}"
    assert f'@undo_grouped(client, "{tool}")' in match.group(1), tool
    # The MCP registration must stay the outermost decorator.
    assert match.group(1).index("@mcp.tool()") < match.group(1).index("@undo_grouped")


# ---- undo tools that take a step count -----------------------------------

@pytest.mark.parametrize("steps", [1, 2, 50, _MAX_UNDO_STEPS])
def test_valid_step_counts_pass(steps):
    _check_undo_steps(steps)


@pytest.mark.parametrize("steps", [0, -1, _MAX_UNDO_STEPS + 1, True, 1.5, "3", None])
def test_invalid_step_counts_are_refused(steps):
    with pytest.raises(ReaperMCPError) as raised:
        _check_undo_steps(steps)
    assert raised.value.code == ErrorCode.VALUE_OUT_OF_RANGE


def test_the_python_step_limit_matches_the_lua_one():
    lua = (ROOT / "reaper_scripts" / "reaper_mcp_server.lua").read_text(encoding="utf-8")
    assert f"local MAX_UNDO_STEPS = {_MAX_UNDO_STEPS}" in lua
