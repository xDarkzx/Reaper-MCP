"""Source-level guards for marker_add/marker_add_region/add_markers_batch's
index vs number handling.

Verified live against a real REAPER instance during a hardening pass:
AddProjectMarker2 returns a marker/region's persistent display NUMBER, not
its enumeration INDEX (what marker_get_all/marker_delete/marker_edit key
off). REAPER reuses a freed number once its marker is deleted, so the two
diverge as soon as any earlier marker is deleted - e.g. adding a 4th marker
after deleting the 1st returned number=1 (reused) while its real index was
2. The old code returned that number labeled as (or in add_markers_batch,
literally named) "index", so passing it straight into a follow-up
marker_delete/marker_edit call would silently target the wrong marker.

These are cheap regression guards so a future refactor can't reintroduce
either the missing resolution or the misleading field name.
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


def test_find_marker_index_helper_matches_by_number_and_region_flag():
    src = LUA.read_text(encoding="utf-8")
    helper = src[src.index("local function find_marker_index"):]
    helper = helper[: helper.index("\nend\n")]
    assert "num == number" in helper
    assert "isrgn == is_region" in helper


class TestMarkerAddLua:
    def test_resolves_real_index(self):
        src = LUA.read_text(encoding="utf-8")
        body = _function_body(src, "function marker.marker_add(p)", "total_markers")
        assert "find_marker_index(num, false)" in body
        assert "marker_index = index" in body


class TestMarkerAddRegionLua:
    def test_resolves_real_index(self):
        src = LUA.read_text(encoding="utf-8")
        body = _function_body(src, "function marker.marker_add_region(p)", "total_markers")
        assert "find_marker_index(num, true)" in body
        assert "marker_index = index" in body


class TestAddMarkersBatchLua:
    def test_resolves_index_after_all_inserts_not_per_entry(self):
        src = LUA.read_text(encoding="utf-8")
        body = _function_body(src, "function compose.add_markers_batch(p)", "items_added")
        assert "r.index = find_marker_index(r.number, r.is_region)" in body
        # The old bug: AddProjectMarker2's return handed straight back as
        # "index" with no resolution step at all.
        assert "index = idx" not in body
