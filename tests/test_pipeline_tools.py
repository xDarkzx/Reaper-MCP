"""Tests for reaper_mcp/tools/pipeline_tools.py.

compute_items_extent is a pure function (no REAPER/IPC mocking needed),
extracted specifically so bounce_stems' core bug fix - computing a real
time-selection range before invoking a REAPER action whose actual name is
"...obeying time selection" - is directly testable.
"""

from reaper_mcp.tools.pipeline_tools import compute_items_extent


def _item(position, length):
    return {"position": position, "length": length}


def test_compute_items_extent_empty_list_returns_none_start():
    min_start, max_end = compute_items_extent([])
    assert min_start is None
    assert max_end == 0.0


def test_compute_items_extent_single_item():
    min_start, max_end = compute_items_extent([_item(2.0, 4.0)])
    assert min_start == 2.0
    assert max_end == 6.0


def test_compute_items_extent_multiple_items_spans_full_range():
    # Regression test for the real bug: bounce_stems used to invoke
    # REAPER's "Render tracks to stereo stem tracks, obeying time
    # selection" action with whatever time selection happened to be
    # active (often none at all) - stems could come back blank even
    # though the item content covered a much wider range. The render
    # range must span from the earliest item's start to the latest
    # item's end across ALL given tracks, not just one.
    items = [
        _item(5.0, 3.0),   # ends at 8.0
        _item(0.0, 2.0),   # starts at 0.0 - the real minimum
        _item(10.0, 1.5),  # ends at 11.5 - the real maximum
    ]
    min_start, max_end = compute_items_extent(items)
    assert min_start == 0.0
    assert max_end == 11.5


def test_compute_items_extent_ignores_item_order():
    forward = [_item(0.0, 1.0), _item(10.0, 1.0)]
    backward = [_item(10.0, 1.0), _item(0.0, 1.0)]
    assert compute_items_extent(forward) == compute_items_extent(backward)
