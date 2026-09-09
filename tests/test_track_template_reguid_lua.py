"""Source-level guard for track_set_state_chunk's TRACKID handling.

Verified live against a real REAPER instance during a hardening pass: saving
track A's state chunk (track_template_save) and applying it to track B
(track_template_apply -> track_set_state_chunk -> SetTrackStateChunk) left
track B with the exact same TRACKID as track A. With track A still in the
project, that's two live tracks sharing one identity - the same class of bug
fixed for items in item_duplicate/item_clone_to_position (see
test_item_duplicate_lua.py, test_chop_pipeline_index_lua.py), just at the
track level via REAPER's region render matrix / other per-track GUID
references instead of the MIDI event pool.

This is a cheap regression guard so a future refactor of
track_set_state_chunk can't silently reintroduce it.
"""

from pathlib import Path

LUA = (
    Path(__file__).resolve().parent.parent
    / "reaper_scripts"
    / "reaper_mcp_server.lua"
)


def test_track_set_state_chunk_reguides_trackid():
    src = LUA.read_text(encoding="utf-8")
    start = src.index("function track.track_set_state_chunk(p)")
    end = src.index("\nend\n", start)
    body = src[start:end]
    assert "reguid_track_chunk(p.chunk)" in body
    assert "SetTrackStateChunk(tr, p.chunk," not in body


def test_reguid_track_chunk_helper_targets_trackid():
    src = LUA.read_text(encoding="utf-8")
    helper = src[src.index("local function reguid_track_chunk"):]
    helper = helper[: helper.index("\nend\n")]
    assert "TRACKID" in helper
