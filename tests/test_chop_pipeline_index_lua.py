"""Source-level guards for item_clone_to_position and chops_create_virtual_slice.

Both handlers live in reaper_scripts/reaper_mcp_server.lua and, like every
other Lua handler in this repo, have no runtime test — they need a live
REAPER. They had the same two defects fixed in item_duplicate (see
test_item_duplicate_lua.py) that a hardening pass found unfixed here:

  - item_clone_to_position copied the source item's chunk verbatim, so a
    stack_chop_layers harmony layer sharing a MIDI item would alias the
    source's event pool (editing one layer's notes edits them all);
  - both handlers returned a pre-insert CountMediaItems() as the new item's
    index, which is wrong as soon as there's an item on any later track -
    exactly the scenario chop_pipeline and stack_chop_layers create by
    placing chops/layers across multiple tracks in a loop.

These are cheap regression guards so a future refactor can't reintroduce
either defect in these two handlers.
"""

from pathlib import Path

LUA = (
    Path(__file__).resolve().parent.parent
    / "reaper_scripts"
    / "reaper_mcp_server.lua"
)


def _function_body(src: str, signature: str, end_anchor: str) -> str:
    start = src.index(signature)
    end = src.index("\nend\n", src.index(end_anchor, start))
    return src[start:end]


class TestItemCloneToPositionLua:
    def test_clone_chunk_is_reguided(self):
        src = LUA.read_text(encoding="utf-8")
        body = _function_body(
            src, "function item.item_clone_to_position(p)", "length = source_length"
        )
        assert "reguid_item_chunk(chunk)" in body
        assert "SetItemStateChunk(new_item, chunk," not in body

    def test_index_resolved_after_insertion(self):
        src = LUA.read_text(encoding="utf-8")
        body = _function_body(
            src, "function item.item_clone_to_position(p)", "length = source_length"
        )
        assert "GetMediaItem(0, i) == new_item" in body
        assert "count_before" not in body


class TestChopsCreateVirtualSliceLua:
    def test_index_resolved_after_insertion(self):
        src = LUA.read_text(encoding="utf-8")
        body = _function_body(
            src,
            "function item.chops_create_virtual_slice(p)",
            "playrate = p.playrate or 1.0",
        )
        assert "GetMediaItem(0, i) == new_item" in body
        assert "count_before" not in body
