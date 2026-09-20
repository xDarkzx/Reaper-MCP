"""FX handlers validate fx_index against the chain instead of calling REAPER blind.

REAPER's TrackFX_* functions quietly do nothing for an index that does not
exist, so a handler that skips the check reports success for an FX that was
never touched - the caller believes `fx_enable(track, 99)` worked. All
handlers that act on an existing FX slot go through `get_fx_index`, which
returns a clear "out of range (chain has N)" error instead.
"""

from pathlib import Path

import pytest

LUA_SRC = (
    Path(__file__).resolve().parent.parent
    / "reaper_scripts"
    / "reaper_mcp_server.lua"
)

# Every fx.* handler that takes the index of an FX already in the chain.
# (fx_get_pin_mappings and fx_remove_batch do their own bounds handling.)
FX_INDEX_HANDLERS = [
    "fx_enable",
    "fx_disable",
    "fx_get_params",
    "fx_get_preset",
    "fx_move",
    "fx_navigate_preset",
    "fx_rename",
    "fx_scan_params",
    "fx_set_param",
    "fx_set_param_by_name",
    "fx_set_preset",
    "fx_show_ui",
]


def _source() -> str:
    return LUA_SRC.read_text(encoding="utf-8")


def _handler_body(name: str) -> str:
    source = _source()
    start = source.index(f"function fx.{name}(p)")
    return source[start: source.index("\nend\n", start)]


@pytest.mark.parametrize("name", FX_INDEX_HANDLERS)
def test_handler_validates_fx_index_against_the_chain(name):
    body = _handler_body(name)
    assert "get_fx_index(tr, p" in body, name
    assert 'require_int(p, "fx_index")' not in body, name
    assert "math.floor(p.fx_index)" not in body, name


def test_fx_move_also_validates_the_target_position():
    assert 'get_fx_index(tr, p, "new_index")' in _handler_body("fx_move")


def _load_helper(lupa, chain_length=3):
    """Run the real get_fx_index under a stubbed `reaper` with N FX in the chain."""
    source = _source()
    start = source.index("local function get_fx_index")
    end = source.index("\nend\n", start) + len("\nend\n")
    runtime = lupa.LuaRuntime()
    runtime.execute(
        f"reaper = {{ TrackFX_GetCount = function(_) return {chain_length} end }}"
    )
    get_fx_index = runtime.execute(source[start:end] + "\nreturn get_fx_index")

    def call(params, key=None):
        return get_fx_index("TRACK", runtime.table_from(params), key)

    return call


@pytest.mark.parametrize("value,expected", [(0, 0), (2, 2), (1.9, 1), ("2", 2)])
def test_valid_indices_resolve(value, expected):
    lupa = pytest.importorskip("lupa")
    call = _load_helper(lupa)
    assert call({"fx_index": value}) == expected


@pytest.mark.parametrize("value", [3, 99, -1])
def test_out_of_range_reports_the_chain_length(value):
    lupa = pytest.importorskip("lupa")
    call = _load_helper(lupa)
    result, err = call({"fx_index": value})
    assert result is None
    assert "out of range" in err and "chain has 3" in err


def test_empty_chain_rejects_every_index():
    lupa = pytest.importorskip("lupa")
    call = _load_helper(lupa, chain_length=0)
    result, err = call({"fx_index": 0})
    assert result is None and "chain has 0" in err


def test_missing_and_non_numeric_are_reported_by_key():
    lupa = pytest.importorskip("lupa")
    call = _load_helper(lupa)
    result, err = call({})
    assert result is None and "fx_index" in err
    result, err = call({"fx_index": "abc"})
    assert result is None and "must be a number" in err
    result, err = call({"new_index": 7}, "new_index")
    assert result is None and "new_index" in err
