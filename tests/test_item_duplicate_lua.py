"""Source-level guards for the item_duplicate Lua handler.

The handler lives in reaper_scripts/reaper_mcp_server.lua and, like every
other Lua handler in this repo, has no runtime test — it needs a live REAPER.
These two assertions are cheap regression guards for the specific defects
fixed in this change, so a future refactor of item_duplicate can't silently
reintroduce them:

  1. clone chunks must be re-GUIDed, or MIDI copies come back pooled with
     the source (editing one edits both);
  2. clone indices must be resolved after every insert, because
     AddMediaItemToTrack shifts the project-wide item enumeration.
"""

from pathlib import Path

import pytest

LUA = (
    Path(__file__).resolve().parent.parent
    / "reaper_scripts"
    / "reaper_mcp_server.lua"
)


@pytest.fixture(scope="module")
def item_duplicate_body() -> str:
    src = LUA.read_text(encoding="utf-8")
    start = src.index("function item.item_duplicate(p)")
    end = src.index("\nend\n", src.index("copies_created", start))
    return src[start:end]


class TestItemDuplicateLua:
    def test_clone_chunk_is_reguided(self, item_duplicate_body: str):
        """The source chunk must not be handed to SetItemStateChunk verbatim."""
        assert "reguid_item_chunk(chunk)" in item_duplicate_body
        assert "SetItemStateChunk(new_item, chunk," not in item_duplicate_body

    def test_clone_indices_resolved_after_insertion(self, item_duplicate_body: str):
        """Indices come from a post-insert scan, not from CountMediaItems()."""
        assert "index_of[c.ptr]" in item_duplicate_body
        assert "count_before" not in item_duplicate_body


def test_reguid_helper_covers_all_three_identity_keys():
    src = LUA.read_text(encoding="utf-8")
    helper = src[src.index("local function reguid_item_chunk"):]
    helper = helper[: helper.index("\nend\n")]
    for key in ("GUID", "IGUID", "POOLEDEVTS"):
        assert f'"{key}"' in helper
