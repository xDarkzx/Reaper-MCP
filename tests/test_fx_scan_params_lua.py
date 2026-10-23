"""fx_scan_params doesn't crash when TrackFX_GetParameterStepCount is missing.

Confirmed live against a real REAPER install: calling
reaper.TrackFX_GetParameterStepCount throws "attempt to call a nil value"
on at least one install, crashing the whole scan for every plugin (ReaComp
and ReaLimit were the two hit during this session's verification). The
call is now guarded so a missing function falls through to the existing
continuous-sweep path instead.

These run the real handler under lupa with a stubbed `reaper`.
"""

from pathlib import Path

import pytest

LUA_SRC = (
    Path(__file__).resolve().parent.parent
    / "reaper_scripts"
    / "reaper_mcp_server.lua"
)


def _load_handler(lupa, *, with_step_count: bool, step_count_value: float = 3):
    """Return call(params): runs fx.fx_scan_params with a stubbed reaper.

    with_step_count=False reproduces the crash condition (the function
    doesn't exist on the stubbed `reaper` table at all, same as the real
    install where this crashed)."""
    source = LUA_SRC.read_text(encoding="utf-8")
    start = source.index("function fx.fx_scan_params(p)")
    end = source.index("\nend\n", start)
    runtime = lupa.LuaRuntime()
    runtime.execute(
        """
        fx = {}
        function get_track(p) return "TRACK0", p.track_index, nil end
        function get_fx_index(tr, p) return p.fx_index, nil end

        reaper = {
          TrackFX_GetNumParams = function(tr, fi) return 1 end,
          TrackFX_GetParamName = function(tr, fi, i, buf) return true, "Test Param" end,
          TrackFX_GetParam = function(tr, fi, i) return 0.5 end,
          TrackFX_SetParam = function(tr, fi, i, v) end,
          TrackFX_FormatParamValue = function(tr, fi, i, v, buf) return true, tostring(v) end,
          TrackFX_GetFXName = function(tr, fi, buf) return true, "Test FX" end,
        }
        """
    )
    if with_step_count:
        runtime.execute(
            f"""
            reaper.TrackFX_GetParameterStepCount = function(tr, fi, i) return {step_count_value} end
            """
        )
    runtime.execute(source[start:end] + "\nend\n")
    handler = runtime.eval("fx.fx_scan_params")

    def call(params):
        return handler(runtime.table_from(params))

    return call


def test_missing_step_count_function_falls_back_to_continuous_sweep_instead_of_crashing():
    lupa = pytest.importorskip("lupa")
    call = _load_handler(lupa, with_step_count=False)
    result = call({"track_index": 0, "fx_index": 0})
    assert result is not None
    params = list(result["params"].values())
    assert len(params) == 1
    samples = list(params[0]["samples"].values())
    # The dense continuous sweep has 9 points.
    assert len(samples) == 9


def test_present_step_count_function_still_uses_stepped_sweep():
    lupa = pytest.importorskip("lupa")
    call = _load_handler(lupa, with_step_count=True, step_count_value=3)
    result = call({"track_index": 0, "fx_index": 0})
    params = list(result["params"].values())
    samples = list(params[0]["samples"].values())
    # step_count=3 means 4 real values (s/3 for s=0..3), per the stepped path.
    assert len(samples) == 4
