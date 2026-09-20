"""The fx_* tools address the master track as track_index -1.

REAPER keeps the master track outside the numbered track list:
GetTrack(0, i) never returns it, GetMasterTrack(0) does, and the TrackFX_*
functions accept either. The Lua bridge's get_track helper maps -1 to the
master track, and the fx tools' index check admits -1 and nothing below it.
"""

from pathlib import Path

import pytest

from reaper_mcp.tools.fx_tools import MASTER_TRACK_INDEX, _check_track_index
from reaper_mcp_shared.error_codes import ErrorCode, ReaperMCPError

ROOT = Path(__file__).resolve().parent.parent
LUA = ROOT / "reaper_scripts" / "reaper_mcp_server.lua"
FX_TOOLS = ROOT / "reaper_mcp" / "tools" / "fx_tools.py"


def test_master_and_numbered_tracks_pass_the_index_check():
    for index in (MASTER_TRACK_INDEX, 0, 7):
        _check_track_index(index)


def test_an_index_below_the_master_track_is_refused():
    with pytest.raises(ReaperMCPError) as raised:
        _check_track_index(-2)
    assert raised.value.code == ErrorCode.VALUE_OUT_OF_RANGE


def test_every_fx_tool_uses_the_shared_index_check():
    source = FX_TOOLS.read_text(encoding="utf-8")
    assert "track_index < 0" not in source
    assert source.count("_check_track_index(track_index)") >= 14


def test_lua_get_track_resolves_the_master_track():
    source = LUA.read_text(encoding="utf-8")
    helper = source[source.index("local function get_track"):]
    helper = helper[: helper.index("\nend\n")]
    assert "MASTER_TRACK_INDEX" in helper
    assert "reaper.GetMasterTrack(0)" in helper
    assert "local MASTER_TRACK_INDEX = -1" in source
