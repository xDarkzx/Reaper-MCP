"""item_insert_media returns the item it actually inserted, with its real index.

It used to return the track's last item and the project's last index. A
track's items are ordered by position, so inserting before an existing item
handed back that other item; and the project's last index is only on this
track when it is the bottom track. load_loops' tempo matching changes the
returned item's playrate, so a wrong item meant stretching the wrong loop.

It also must not go through InsertMedia: REAPER's import routine can stop
on a prompt ("Media contains embedded tempo information, import as:") that
blocks the bridge until someone answers it in REAPER - confirmed live with
ACID-tagged sample-pack loops - and its answer can stretch the item itself.

These run the real handler under lupa with a stubbed `reaper` that keeps
items in REAPER's order (by track, then by position).
"""

from pathlib import Path

import pytest

LUA_SRC = (
    Path(__file__).resolve().parent.parent
    / "reaper_scripts"
    / "reaper_mcp_server.lua"
)


def _load_handler(lupa, *, insert_fails: bool = False):
    """Return call(params), with the Lua runtime on call.runtime. Tracks
    start as: track 0 has an item at 10s, track 1 has an item at 0s."""
    source = LUA_SRC.read_text(encoding="utf-8")
    start = source.index("function item.item_insert_media(p)")
    end = source.index("\nend\n", start)
    runtime = lupa.LuaRuntime()
    runtime.execute(
        """
        item = {}
        tracks = {
          {items = {{name = "existing_t0", pos = 10.0}}},
          {items = {{name = "existing_t1", pos = 0.0}}},
        }
        insert_fails = false
        destroyed = 0

        function basename(path) return path:match("([^\\\\/]+)$") or path end

        function build_item_info(it, idx)
          local take = it.take or {}
          return {
            name = it.name, index = idx, length = it.D_LENGTH, position = it.D_POSITION,
            playrate = take.D_PLAYRATE or 1.0, preserve_pitch = take.B_PPITCH,
            take_name = take.P_NAME,
          }
        end

        local function sorted(list)
          local copy = {}
          for i, v in ipairs(list) do copy[i] = v end
          table.sort(copy, function(a, b) return (a.D_POSITION or a.pos) < (b.D_POSITION or b.pos) end)
          return copy
        end

        reaper = {
          GetTrack = function(_, i) return tracks[i + 1] end,
          CountTrackMediaItems = function(tr) return #tr.items end,
          GetTrackMediaItem = function(tr, i) return sorted(tr.items)[i + 1] end,
          PCM_Source_CreateFromFile = function(path)
            if path == "missing.wav" then return nil end
            if path == "empty.wav" then return {len = 0} end
            return {len = 8.0}
          end,
          GetMediaSourceLength = function(src) return src.len, false end,
          PCM_Source_Destroy = function(src) destroyed = destroyed + 1 end,
          AddMediaItemToTrack = function(tr)
            if insert_fails then return nil end
            local it = {name = "inserted", D_POSITION = 0}
            tr.items[#tr.items + 1] = it
            return it
          end,
          AddTakeToMediaItem = function(it) it.take = {}; return it.take end,
          SetMediaItemTake_Source = function(take, src) take.src = src end,
          GetSetMediaItemTakeInfo_String = function(take, key, v, set) take[key] = v; return true, v end,
          UpdateArrange = function() end,
          GetActiveTake = function(it) return it.take end,
          SetMediaItemTakeInfo_Value = function(take, key, v) take[key] = v end,
          GetMediaItemInfo_Value = function(it, key) return it[key] end,
          SetMediaItemInfo_Value = function(it, key, v) it[key] = v end,
          CountMediaItems = function()
            local n = 0
            for _, t in ipairs(tracks) do n = n + #t.items end
            return n
          end,
          GetMediaItem = function(_, gi)
            for _, t in ipairs(tracks) do
              local items = sorted(t.items)
              if gi < #items then return items[gi + 1] end
              gi = gi - #items
            end
            return nil
          end,
        }
        """
    )
    if insert_fails:
        runtime.execute("insert_fails = true")
    runtime.execute(source[start:end] + "\nend\n")
    handler = runtime.eval("item.item_insert_media")

    def call(params):
        return handler(runtime.table_from(params))

    call.runtime = runtime
    return call


def test_insert_before_existing_item_returns_the_inserted_item():
    lupa = pytest.importorskip("lupa")
    call = _load_handler(lupa)
    result = call({"track_index": 0, "path": "loop.wav", "position": 0.0})
    assert result["name"] == "inserted"
    # Global order: track 0 = [inserted@0, existing_t0@10], track 1 = [...].
    assert result["index"] == 0


def test_insert_on_upper_track_reports_index_within_that_track_block():
    lupa = pytest.importorskip("lupa")
    call = _load_handler(lupa)
    result = call({"track_index": 0, "path": "loop.wav", "position": 20.0})
    assert result["name"] == "inserted"
    # After existing_t0, but before track 1's item - not the project's last.
    assert result["index"] == 1


def test_insert_on_bottom_track():
    lupa = pytest.importorskip("lupa")
    call = _load_handler(lupa)
    result = call({"track_index": 1, "path": "loop.wav", "position": 4.0})
    assert result["name"] == "inserted"
    assert result["index"] == 2


def test_no_playrate_leaves_the_take_untouched():
    lupa = pytest.importorskip("lupa")
    call = _load_handler(lupa)
    result = call({"track_index": 0, "path": "loop.wav", "position": 0.0})
    assert result["playrate"] == 1.0
    assert result["preserve_pitch"] is None
    assert result["length"] == 8.0


def test_playrate_sets_rate_keeps_pitch_and_resizes_item():
    lupa = pytest.importorskip("lupa")
    call = _load_handler(lupa)
    # A 120 BPM loop into a 128 BPM project: rate 128/120.
    rate = 128 / 120
    result = call({"track_index": 0, "path": "loop.wav", "position": 0.0, "playrate": rate})
    assert result["playrate"] == pytest.approx(rate)
    assert result["preserve_pitch"] == 1
    assert result["length"] == pytest.approx(8.0 / rate)


def test_preserve_pitch_false_is_respected():
    lupa = pytest.importorskip("lupa")
    call = _load_handler(lupa)
    result = call({
        "track_index": 0, "path": "loop.wav", "position": 0.0,
        "playrate": 0.5, "preserve_pitch": False,
    })
    assert result["preserve_pitch"] == 0
    assert result["length"] == pytest.approx(16.0)


@pytest.mark.parametrize("bad", [0, -1.0, "abc"])
def test_bad_playrate_is_rejected_before_anything_is_inserted(bad):
    lupa = pytest.importorskip("lupa")
    call = _load_handler(lupa)
    result, err = call({"track_index": 0, "path": "loop.wav", "position": 0.0, "playrate": bad})
    assert result is None
    assert err == "playrate must be > 0"
    # Nothing was added to track 0.
    assert call.runtime.eval("#tracks[1].items") == 1


def test_failed_insert_is_an_error_not_another_item():
    lupa = pytest.importorskip("lupa")
    call = _load_handler(lupa, insert_fails=True)
    result, err = call({"track_index": 0, "path": "loop.wav", "position": 0.0})
    assert result is None
    assert err == "Media insert failed"
    assert call.runtime.eval("destroyed") == 1


def test_unopenable_file_is_an_error_and_adds_nothing():
    lupa = pytest.importorskip("lupa")
    call = _load_handler(lupa)
    result, err = call({"track_index": 0, "path": "missing.wav", "position": 0.0})
    assert result is None
    assert err.startswith("Could not open media file")
    assert call.runtime.eval("#tracks[1].items") == 1


def test_empty_file_is_an_error_and_adds_nothing():
    lupa = pytest.importorskip("lupa")
    call = _load_handler(lupa)
    result, err = call({"track_index": 0, "path": "empty.wav", "position": 0.0})
    assert result is None
    assert err.startswith("Media file has no readable audio")
    assert call.runtime.eval("#tracks[1].items") == 1
    assert call.runtime.eval("destroyed") == 1


def test_item_placed_at_position_with_source_length_and_file_name():
    lupa = pytest.importorskip("lupa")
    call = _load_handler(lupa)
    result = call({"track_index": 0, "path": "D:\\Loops\\Pad_131bpm.wav", "position": 3.2})
    assert result["position"] == pytest.approx(3.2)
    assert result["length"] == pytest.approx(8.0)
    assert result["take_name"] == "Pad_131bpm.wav"


def test_does_not_use_reapers_import_routine():
    """InsertMedia can block the bridge on an import prompt; see module doc."""
    source = LUA_SRC.read_text(encoding="utf-8")
    start = source.index("function item.item_insert_media(p)")
    body = source[start:source.index("\nend\n", start)]
    code = "\n".join(l.split("--")[0] for l in body.splitlines())
    assert "InsertMedia(" not in code
    assert "PCM_Source_CreateFromFile" in code
