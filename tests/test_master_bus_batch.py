"""Batch tools can address the master track as track_index -1.

PR #34 gave the single-track fx_* tools master access via get_track. That
covers reading and modifying an existing master chain, but not building one:
setup_fx_chain is the only tool that can ADD an FX, and it resolved tracks
with reaper.GetTrack directly, so a mastering chain could only be created by
setup_master_chain / engine_master, which replace whatever is already there.

These cover the batch entry points, which take a raw numeric index per entry
rather than a params table and so cannot use get_track.
"""

from pathlib import Path

import pytest

from reaper_mcp.tools.compose_edit_tools import MASTER_TRACK_INDEX
from reaper_mcp_shared.error_codes import ErrorCode, ReaperMCPError

ROOT = Path(__file__).resolve().parent.parent
LUA = ROOT / "reaper_scripts" / "reaper_mcp_server.lua"


def _lua_body(source: str, signature: str) -> str:
    body = source[source.index(signature):]
    return body[: body.index("\nend\n")]


def test_master_index_constant_matches_the_fx_tools_convention():
    from reaper_mcp.tools.fx_tools import MASTER_TRACK_INDEX as FX_MASTER
    assert MASTER_TRACK_INDEX == FX_MASTER == -1


def test_batch_resolver_maps_minus_one_to_the_master_track():
    body = _lua_body(LUA.read_text(encoding="utf-8"), "local function batch_track_from_index")
    assert "MASTER_TRACK_INDEX" in body
    assert "reaper.GetMasterTrack(0)" in body


@pytest.mark.parametrize("signature", [
    "function compose.setup_fx_chain",
    "function compose.configure_tracks",
])
def test_batch_entry_points_resolve_through_the_batch_resolver(signature):
    body = _lua_body(LUA.read_text(encoding="utf-8"), signature)
    assert "batch_track_from_index(ti)" in body
    assert "reaper.GetTrack(0, ti)" not in body


def test_only_the_batch_entry_points_gained_minus_one_access():
    # Guard against a blanket "allow -1 everywhere" refactor: track_rename
    # and track_freeze resolve through get_track, so widening access
    # carelessly would expose them to the master track. (Deleting is
    # separately refused in Lua - see test_lua_master_guard.py.)
    source = LUA.read_text(encoding="utf-8")
    call_sites = source.count("= batch_track_from_index(ti)")
    assert call_sites == 2, f"expected 2 batch call sites, found {call_sites}" 


def test_pr34_get_track_still_resolves_the_master_itself():
    # Regression guard for the merged contribution: the single-track fx_*
    # path must keep working even if the batch resolver is refactored.
    body = _lua_body(LUA.read_text(encoding="utf-8"), "local function get_track")
    assert "reaper.GetMasterTrack(0)" in body


def test_configure_tracks_admits_master_and_refuses_below_it():
    import asyncio
    from unittest.mock import AsyncMock, patch
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("t")
    client = AsyncMock()
    client.execute = AsyncMock(return_value={"success": True})
    with patch("reaper_mcp.main.client", client):
        from reaper_mcp.tools.compose_edit_tools import register
        register(mcp)
    fn = mcp._tool_manager._tools["configure_tracks"].fn

    asyncio.run(fn(tracks='[{"track_index": -1, "volume_db": -2.0}]'))
    assert client.execute.await_count == 1

    with pytest.raises(ReaperMCPError) as raised:
        asyncio.run(fn(tracks='[{"track_index": -2}]'))
    assert raised.value.code == ErrorCode.VALUE_OUT_OF_RANGE
