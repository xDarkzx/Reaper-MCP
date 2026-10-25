"""apply_named_config writes plugin named-config values and trusts only the read-back.

Issue #44: ReaEQ's high-pass band ships disabled and its enable state isn't
an automatable param. TrackFX_SetNamedConfigParm returned false for
BANDENABLED4 even though the write took effect (confirmed by read-back and
audio), so success must come from TrackFX_GetNamedConfigParm.
"""

from pathlib import Path

import pytest

LUA_SRC = Path(__file__).resolve().parent.parent / "reaper_scripts" / "reaper_mcp_server.lua"


def _apply(stub: str):
    lupa = pytest.importorskip("lupa")
    source = LUA_SRC.read_text(encoding="utf-8")
    start = source.index("local function sorted_name_pairs")
    end = source.index("local function build_fx_chain")
    rt = lupa.LuaRuntime()
    rt.execute(stub)
    fn = rt.execute(source[start:end] + "\nreturn apply_named_config\n")
    return rt, fn


STORE_STUB = """
store = {}
reaper = {
  TrackFX_SetNamedConfigParm = function(tr, fx, key, val) store[key] = val; return false end,
  TrackFX_GetNamedConfigParm = function(tr, fx, key) return store[key] ~= nil, store[key] or "" end,
}
"""


def test_write_reported_ok_from_readback_even_when_setter_returns_false():
    rt, apply = _apply(STORE_STUB)
    results = apply("TR", 0, rt.table_from({"BANDENABLED4": "1"}))
    r = results[1]
    assert r["key"] == "BANDENABLED4"
    assert r["value"] == "1"
    assert r["ok"] is True
    assert rt.eval("store.BANDENABLED4") == "1"


def test_write_that_does_not_stick_is_reported_not_ok():
    stub = """
    reaper = {
      TrackFX_SetNamedConfigParm = function() return true end,
      TrackFX_GetNamedConfigParm = function() return true, "0" end,
    }
    """
    rt, apply = _apply(stub)
    results = apply("TR", 0, rt.table_from({"BANDENABLED4": "1"}))
    assert results[1]["ok"] is False
    assert results[1]["value"] == "0"


def test_missing_api_reports_error_instead_of_crashing():
    rt, apply = _apply("reaper = {}")
    results = apply("TR", 0, rt.table_from({"BANDENABLED4": "1"}))
    assert "6.37" in results[1]["error"]


def test_no_named_config_is_a_no_op():
    rt, apply = _apply(STORE_STUB)
    results = apply("TR", 0, None)
    assert len(results) == 0
