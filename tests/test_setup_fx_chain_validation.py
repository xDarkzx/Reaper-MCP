"""setup_fx_chain validates its input before anything reaches REAPER.

It is the main entry point for adding plugins and writing parameters, but
used to check only that each entry had a track_index. A non-dict entry raised
a raw TypeError, a chain item with neither a name nor an fx_index was
silently skipped (a "success" that did nothing), and there was no cap on
entries. It now fails fast with the same clear per-entry errors as the
sibling batch tools.
"""

import json

import pytest

from reaper_mcp.tools.compose_edit_tools import (
    _MAX_SETUP_FX_CHAIN_ENTRIES,
    _validate_setup_fx_chain_entries,
)
from reaper_mcp_shared.error_codes import ErrorCode, ReaperMCPError


def _ok(entries):
    _validate_setup_fx_chain_entries(entries)


def _bad(entries, code=None):
    with pytest.raises(ReaperMCPError) as raised:
        _validate_setup_fx_chain_entries(entries)
    if code is not None:
        assert raised.value.code == code
    return str(raised.value)


# ---- shapes that must keep working ---------------------------------------

def test_documented_examples_are_accepted():
    _ok([{"track_index": 0, "fx_chain": [{"name": "FabFilter Pro-Q 3"}]}])
    _ok([{"track_index": 0, "fx_chain": [
        {"fx_index": 1, "params_by_index": {"0": 1.0, "8": 0.25}},
        {"fx_index": 1, "params_by_index": {"13": 1.0, "21": 0.375}},
    ]}])
    _ok([{"track_index": 2, "fx_chain": [
        {"name": "ReaComp", "add_mode": "find_or_add",
         "params": {"Threshold": 0.4}, "preset": "Vocal"},
    ]}])


def test_master_track_and_a_track_without_fx_chain_are_accepted():
    _ok([{"track_index": -1, "fx_chain": [{"name": "ReaLimit"}]}])
    _ok([{"track_index": 3}])


def test_fx_chain_may_be_a_json_string_as_the_lua_side_allows():
    _ok([{"track_index": 0, "fx_chain": json.dumps([{"name": "ReaEQ"}])}])


@pytest.mark.parametrize("mode", ["add", "find_or_add", "find_only"])
def test_known_add_modes_are_accepted(mode):
    _ok([{"track_index": 0, "fx_chain": [{"name": "ReaEQ", "add_mode": mode}]}])


# ---- entry level ----------------------------------------------------------

@pytest.mark.parametrize("entries", [[], {}, "x", None, 5])
def test_entries_must_be_a_non_empty_array(entries):
    _bad(entries, ErrorCode.INVALID_PARAMETER)


@pytest.mark.parametrize("entry", [5, "abc", None, [1], 1.5])
def test_non_object_entries_are_a_clear_error_not_a_type_error(entry):
    message = _bad([entry], ErrorCode.INVALID_PARAMETER)
    assert "Entry 0" in message


def test_track_index_is_required_and_must_be_an_int():
    assert "track_index" in _bad([{"fx_chain": []}], ErrorCode.INVALID_PARAMETER)
    for bad in ("0", 1.5, True, None):
        _bad([{"track_index": bad}], ErrorCode.INVALID_PARAMETER)


def test_track_index_below_the_master_is_refused():
    _bad([{"track_index": -2}], ErrorCode.VALUE_OUT_OF_RANGE)


def test_entry_count_is_capped():
    entries = [{"track_index": 0}] * (_MAX_SETUP_FX_CHAIN_ENTRIES + 1)
    _bad(entries, ErrorCode.VALUE_OUT_OF_RANGE)
    _ok([{"track_index": 0}] * _MAX_SETUP_FX_CHAIN_ENTRIES)


def test_the_error_names_the_offending_entry():
    entries = [{"track_index": 0}, {"track_index": 1}, {"track_index": "x"}]
    assert "Entry 2" in _bad(entries)


# ---- fx_chain items -------------------------------------------------------

def test_fx_chain_must_be_an_array():
    _bad([{"track_index": 0, "fx_chain": {"name": "ReaEQ"}}], ErrorCode.INVALID_PARAMETER)
    _bad([{"track_index": 0, "fx_chain": "not json"}], ErrorCode.INVALID_PARAMETER)


@pytest.mark.parametrize("item", [5, "ReaEQ", None, ["ReaEQ"]])
def test_fx_chain_items_must_be_objects(item):
    _bad([{"track_index": 0, "fx_chain": [item]}], ErrorCode.INVALID_PARAMETER)


def test_an_item_with_neither_name_nor_fx_index_is_refused_not_skipped():
    message = _bad(
        [{"track_index": 0, "fx_chain": [{"params": {"Gain": 0.5}}]}],
        ErrorCode.INVALID_PARAMETER,
    )
    assert "name" in message and "fx_index" in message


@pytest.mark.parametrize("name", ["", "   ", 5, None])
def test_name_must_be_a_non_empty_string(name):
    _bad([{"track_index": 0, "fx_chain": [{"name": name}]}], ErrorCode.INVALID_PARAMETER)


@pytest.mark.parametrize("fx_index", [-1, 1.5, "1", True])
def test_fx_index_must_be_a_non_negative_int(fx_index):
    _bad([{"track_index": 0, "fx_chain": [{"fx_index": fx_index}]}])


def test_unknown_add_mode_is_refused_instead_of_silently_adding():
    _bad([{"track_index": 0, "fx_chain": [{"name": "ReaEQ", "add_mode": "replace"}]}],
         ErrorCode.INVALID_PARAMETER)


# ---- params ---------------------------------------------------------------

def test_params_must_map_names_to_finite_numbers():
    _bad([{"track_index": 0, "fx_chain": [{"name": "X", "params": [1, 2]}]}])
    _bad([{"track_index": 0, "fx_chain": [{"name": "X", "params": {"Gain": "loud"}}]}])
    _bad([{"track_index": 0, "fx_chain": [{"name": "X", "params": {"Gain": True}}]}])
    _bad([{"track_index": 0, "fx_chain": [{"name": "X", "params": {"Gain": float("nan")}}]}])
    _bad([{"track_index": 0, "fx_chain": [{"name": "X", "params": {"Gain": float("inf")}}]}])


def test_params_by_index_keys_must_be_non_negative_integers_as_strings():
    _ok([{"track_index": 0, "fx_chain": [{"fx_index": 0, "params_by_index": {"0": 0.5, "12": 1}}]}])
    for key in ("-1", "abc", "1.5", ""):
        _bad([{"track_index": 0, "fx_chain": [{"fx_index": 0, "params_by_index": {key: 0.5}}]}])


def test_preset_must_be_a_string():
    _bad([{"track_index": 0, "fx_chain": [{"name": "X", "preset": 5}]}])


def test_param_count_per_item_is_capped():
    big = {str(i): 0.5 for i in range(1001)}
    _bad([{"track_index": 0, "fx_chain": [{"fx_index": 0, "params_by_index": big}]}],
         ErrorCode.VALUE_OUT_OF_RANGE)


def test_fx_per_track_is_capped():
    chain = [{"name": "ReaEQ"}] * 51
    _bad([{"track_index": 0, "fx_chain": chain}], ErrorCode.VALUE_OUT_OF_RANGE)
