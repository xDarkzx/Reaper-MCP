"""Envelope handlers convert values and create envelopes without side effects.

Issue #44, confirmed live on REAPER 7.x before the fix:
- Volume envelopes use fader scaling, so a raw write of 1.0 ("unity" per the
  tool docs) landed near silence (0 dB is ~716 in that scale).
- Pan envelopes store pan negated: a track panned -0.5 seeded its new Pan
  envelope with +0.5.
- Creating an envelope reset the fader/pan, left a seed point at t=0 and
  changed the track selection.

These run the real Lua handlers under lupa against a stubbed `reaper` that
mimics that measured behaviour.
"""

from pathlib import Path

import pytest

LUA_SRC = Path(__file__).resolve().parent.parent / "reaper_scripts" / "reaper_mcp_server.lua"

STUB = """
envelope = {}
function json_decode(s) return nil end

FADER = 716.0  -- stand-in for fader scaling: internal = linear * FADER

state = {
  track = {D_VOL = 0.4467, D_PAN = -0.5, D_WIDTH = 0.8},
  selected = {OTHER = true},
  envs = {},
  inserted = {},
}

local function new_env(name, mode)
  return {name = name, mode = mode, points = {}}
end

reaper = {
  GetTrack = function(proj, i) if i == 0 then return "TR" end return nil end,
  GetTrackEnvelopeByName = function(tr, name) return state.envs[name] end,
  CountSelectedTracks = function()
    local n = 0
    for _, v in pairs(state.selected) do if v then n = n + 1 end end
    return n
  end,
  GetSelectedTrack = function(proj, i)
    local list = {}
    for k, v in pairs(state.selected) do if v then list[#list+1] = k end end
    table.sort(list)
    return list[i + 1]
  end,
  SetOnlyTrackSelected = function(tr) state.selected = {[tr] = true} end,
  SetTrackSelected = function(tr, sel) state.selected[tr] = sel end,
  GetMediaTrackInfo_Value = function(tr, key) return state.track[key] end,
  SetMediaTrackInfo_Value = function(tr, key, v) state.track[key] = v end,
  Main_OnCommand = function(cmd, flag)
    -- Measured behaviour: fader value moves into a seed point, fader resets.
    if cmd == 40406 then
      local e = new_env("Volume", 1)
      e.points[1] = {time = 0, value = state.track.D_VOL * FADER}
      state.track.D_VOL = 1.0
      state.envs["Volume"] = e
    elseif cmd == 40407 then
      local e = new_env("Pan", 0)
      e.points[1] = {time = 0, value = -state.track.D_PAN}
      state.track.D_PAN = 0.0
      state.envs["Pan"] = e
    end
  end,
  DeleteEnvelopePointRange = function(env, t0, t1)
    local keep = {}
    for _, pt in ipairs(env.points) do
      if not (pt.time >= t0 and pt.time < t1) then keep[#keep+1] = pt end
    end
    env.points = keep
  end,
  GetEnvelopeScalingMode = function(env) return env.mode end,
  ScaleToEnvelopeMode = function(mode, v) if mode == 1 then return v * FADER end return v end,
  ScaleFromEnvelopeMode = function(mode, v) if mode == 1 then return v / FADER end return v end,
  InsertEnvelopePoint = function(env, time, value, shape, tension, sel, nosort)
    -- Measured: inserting into an empty envelope also adds a neutral t=0 point.
    if #env.points == 0 and time > 0 then
      env.points[1] = {time = 0, value = (env.mode == 1) and FADER or 0}
    end
    env.points[#env.points+1] = {time = time, value = value}
  end,
  Envelope_SortPoints = function(env)
    table.sort(env.points, function(a, b) return a.time < b.time end)
  end,
  CountEnvelopePoints = function(env) return #env.points end,
  GetEnvelopePoint = function(env, i)
    local pt = env.points[i + 1]
    return true, pt.time, pt.value, 0, 0, false
  end,
  UpdateArrange = function() end,
  GetFXEnvelope = function() return nil end,
}
"""


def _runtime():
    lupa = pytest.importorskip("lupa")
    source = LUA_SRC.read_text(encoding="utf-8")
    start = source.index("local ENVELOPE_CREATE_ACTIONS")
    end = source.index("function envelope.envelope_clear_range")
    rt = lupa.LuaRuntime()
    rt.execute(STUB)
    rt.execute(source[start:end])
    return rt


def _add(rt, params):
    return rt.eval("envelope.envelope_add_points")(rt.table_from(params))


def _get(rt, params):
    return rt.eval("envelope.envelope_get_points")(rt.table_from(params))


def _points(rt, name):
    env = rt.eval(f"state.envs[{name!r}]")
    return [(p["time"], p["value"]) for p in env["points"].values()]


def test_volume_write_is_converted_to_fader_scale():
    rt = _runtime()
    _add(rt, {"track_index": 0, "envelope_name": "Volume", "create": True,
              "points": rt.table_from([rt.table_from({"time": 2.0, "value": 1.0})])})
    assert _points(rt, "Volume") == [(2.0, pytest.approx(716.0))]


def test_volume_read_round_trips_in_linear_gain():
    rt = _runtime()
    _add(rt, {"track_index": 0, "envelope_name": "Volume", "create": True,
              "points": rt.table_from([rt.table_from({"time": 1.0, "value": 0.5})])})
    result = _get(rt, {"track_index": 0, "envelope_name": "Volume"})
    assert result["points"][1]["value"] == pytest.approx(0.5)


def test_creating_volume_envelope_keeps_fader_and_drops_seed_point():
    rt = _runtime()
    _add(rt, {"track_index": 0, "envelope_name": "Volume", "create": True,
              "points": rt.table_from([rt.table_from({"time": 2.0, "value": 1.0})])})
    assert rt.eval("state.track.D_VOL") == pytest.approx(0.4467)
    times = [t for t, _ in _points(rt, "Volume")]
    assert times == [2.0]


def test_creating_envelope_restores_track_selection():
    rt = _runtime()
    _add(rt, {"track_index": 0, "envelope_name": "Volume", "create": True,
              "points": rt.table_from([rt.table_from({"time": 0.0, "value": 1.0})])})
    assert rt.eval("state.selected.OTHER") is True
    assert not rt.eval("state.selected.TR")


def test_pan_is_negated_on_write_and_read():
    rt = _runtime()
    _add(rt, {"track_index": 0, "envelope_name": "Pan", "create": True,
              "points": rt.table_from([rt.table_from({"time": 1.0, "value": 0.25})])})
    assert _points(rt, "Pan") == [(1.0, pytest.approx(-0.25))]
    result = _get(rt, {"track_index": 0, "envelope_name": "Pan"})
    assert result["points"][1]["value"] == pytest.approx(0.25)


def test_creating_pan_envelope_keeps_pan():
    rt = _runtime()
    _add(rt, {"track_index": 0, "envelope_name": "Pan", "create": True,
              "points": rt.table_from([rt.table_from({"time": 1.0, "value": 0.0})])})
    assert rt.eval("state.track.D_PAN") == pytest.approx(-0.5)


def test_missing_envelope_without_create_says_to_pass_create():
    rt = _runtime()
    fn = rt.eval("""function()
      local r, err = envelope.envelope_get_points({track_index = 0, envelope_name = "Volume"})
      return err
    end""")
    assert "Pass create=true" in fn()


def test_width_create_failure_message():
    rt = _runtime()
    fn = rt.eval("""function()
      local r, err = envelope.envelope_add_points({track_index = 0, envelope_name = "Width",
        create = true, points = {{time = 1.0, value = 0.5}}})
      return err
    end""")
    assert fn() == "Track envelope 'Width' could not be created."


def test_new_envelope_has_no_default_point_before_callers_first_point():
    rt = _runtime()
    _add(rt, {"track_index": 0, "envelope_name": "Pan", "create": True,
              "points": rt.table_from([rt.table_from({"time": 1.0, "value": 0.25})])})
    assert [t for t, _ in _points(rt, "Pan")] == [1.0]


def test_existing_envelope_points_before_batch_are_kept():
    rt = _runtime()
    _add(rt, {"track_index": 0, "envelope_name": "Pan", "create": True,
              "points": rt.table_from([rt.table_from({"time": 0.5, "value": 0.1})])})
    _add(rt, {"track_index": 0, "envelope_name": "Pan", "create": True,
              "points": rt.table_from([rt.table_from({"time": 2.0, "value": 0.3})])})
    assert [t for t, _ in _points(rt, "Pan")] == [0.5, 2.0]
