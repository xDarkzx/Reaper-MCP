"""Tests for fx_set_params_batch's validation logic in
reaper_mcp/tools/fx_tools.py.

validate_batch_params is a pure function (no REAPER/IPC mocking needed),
extracted specifically so the batch-param-setting tool's input validation
is directly testable, matching the pattern already used for
pipeline_tools.compute_items_extent.
"""

import pytest

from reaper_mcp.tools.fx_tools import validate_batch_params
from reaper_mcp_shared.constants import MAX_PARAMS_PER_BATCH
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


def _item(**overrides):
    base = {"track_index": 0, "fx_index": 1, "value": 0.5, "param_index": 8}
    base.update(overrides)
    return base


def test_valid_batch_with_param_index_passes():
    validate_batch_params([_item()])


def test_valid_batch_with_param_name_passes():
    item = _item(param_name="Band 1 Shape")
    del item["param_index"]
    validate_batch_params([item])


def test_empty_list_raises():
    with pytest.raises(ReaperMCPError) as exc_info:
        validate_batch_params([])
    assert exc_info.value.code == ErrorCode.INVALID_PARAMETER


def test_non_list_raises():
    with pytest.raises(ReaperMCPError) as exc_info:
        validate_batch_params({"not": "a list"})
    assert exc_info.value.code == ErrorCode.INVALID_PARAMETER


def test_too_many_items_raises():
    items = [_item() for _ in range(MAX_PARAMS_PER_BATCH + 1)]
    with pytest.raises(ReaperMCPError) as exc_info:
        validate_batch_params(items)
    assert exc_info.value.code == ErrorCode.VALUE_OUT_OF_RANGE


def test_exactly_max_items_passes():
    items = [_item() for _ in range(MAX_PARAMS_PER_BATCH)]
    validate_batch_params(items)


def test_non_dict_item_raises():
    with pytest.raises(ReaperMCPError) as exc_info:
        validate_batch_params(["not a dict"])
    assert exc_info.value.code == ErrorCode.INVALID_PARAMETER


def test_missing_required_key_raises():
    for key in ("track_index", "fx_index", "value"):
        item = _item()
        del item[key]
        with pytest.raises(ReaperMCPError, match=key):
            validate_batch_params([item])


def test_both_param_index_and_param_name_raises():
    # Ambiguous - which one wins? Reject rather than guess.
    item = _item(param_name="Band 1 Shape")  # already has param_index too
    with pytest.raises(ReaperMCPError) as exc_info:
        validate_batch_params([item])
    assert exc_info.value.code == ErrorCode.INVALID_PARAMETER
    assert "exactly one" in exc_info.value.message


def test_neither_param_index_nor_param_name_raises():
    item = _item()
    del item["param_index"]
    with pytest.raises(ReaperMCPError, match="exactly one"):
        validate_batch_params([item])


def test_empty_param_name_with_no_param_index_raises():
    # An empty string is falsy - must not count as "param_name given".
    item = _item(param_name="")
    del item["param_index"]
    with pytest.raises(ReaperMCPError, match="exactly one"):
        validate_batch_params([item])


def test_value_out_of_range_raises():
    for bad in (-0.1, 1.1, 2.0):
        with pytest.raises(ReaperMCPError) as exc_info:
            validate_batch_params([_item(value=bad)])
        assert exc_info.value.code == ErrorCode.VALUE_OUT_OF_RANGE


def test_value_boundaries_are_valid():
    validate_batch_params([_item(value=0.0)])
    validate_batch_params([_item(value=1.0)])


def test_non_numeric_value_raises():
    with pytest.raises(ReaperMCPError) as exc_info:
        validate_batch_params([_item(value="0.5")])
    assert exc_info.value.code == ErrorCode.VALUE_OUT_OF_RANGE


def test_error_message_identifies_which_item_index_failed():
    items = [_item(), _item(value=5.0)]
    with pytest.raises(ReaperMCPError, match=r"params\[1\]"):
        validate_batch_params(items)


def test_mixed_valid_and_invalid_items_raises_on_first_bad_one():
    bad_item = _item()
    del bad_item["track_index"]
    items = [_item(), _item(), bad_item]
    with pytest.raises(ReaperMCPError, match=r"params\[2\]"):
        validate_batch_params(items)
