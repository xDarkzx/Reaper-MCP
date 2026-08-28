# VST Parameter Auto-Scan & Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `fx_scan_params` tool that sweeps an FX plugin's parameters once, infers each
one's units/curve shape from REAPER's own formatted display strings, and caches the result to a
shareable, git-trackable JSON file so future scans of the same plugin (in any project) are
instant and don't touch REAPER again.

**Architecture:** A new Lua command handler does the entire sweep (every param, 3 sample points
each) in one IPC round trip and restores original values as it goes. A new Python module infers
curve type from the sampled strings and manages a JSON cache under
`reaper_mcp_shared/plugin_maps/`, checked before ever calling the Lua handler.

**Tech Stack:** Python (reaper_mcp package), Lua (REAPER ReaScript), pytest, existing FastMCP tool
registration pattern.

## Global Constraints

- Cache files are plain JSON, one per plugin, committable to git — NOT written into the private
  `Connection.IPC_DIR` (that directory is per-machine and 0700-restricted; this data is meant to
  be shared, so it must not use `ensure_private_dir`).
- Param-count cap is `MAX_SCAN_PARAMS = 200` (spec: "Error Handling — Param-count cap").
- `fx_scan_params` must use `client.execute_long` (600s timeout), not `client.execute` (30s) —
  spec: "Error Handling — Timeout".
- Sample points are exactly `{0.0, 0.5, 1.0}` normalized value — spec: "Data flow" step 4.
- Skip the same "junk" params `build_fx_params` already skips: unnamed `-` params with value 0,
  and any param whose name matches `^MIDI CC`.
- Cache writes are atomic (`.tmp` file + `os.replace`) and best-effort (`except Exception: pass`
  around the write only, never around the scan itself) — spec: "Error Handling — Cache write".

---

## File Structure

- **Modify:** `reaper_mcp_shared/constants.py` — add `PLUGIN_MAP_DIR` and `MAX_SCAN_PARAMS`.
- **Create:** `reaper_mcp_shared/plugin_maps/.gitkeep` — makes the empty cache directory
  trackable by git before any scan has run.
- **Create:** `reaper_mcp_shared/plugin_maps/README.md` — one-paragraph explanation of what
  these files are, for anyone who stumbles on the directory or opens a PR adding one.
- **Create:** `reaper_mcp_shared/plugin_cache.py` — `sanitize_plugin_name`, `infer_curve`,
  `load_cached_map`, `save_cached_map`. Pure logic, no REAPER/IPC dependency.
- **Create:** `tests/test_plugin_cache.py` — unit tests for everything in `plugin_cache.py`.
- **Modify:** `reaper_scripts/reaper_mcp_server.lua` — add `function fx.fx_scan_params(p)` next to
  the other `fx.*` handlers (around line 1342, after `fx.fx_set_param_by_name`). No dispatch-table
  change needed — `for k, v in pairs(fx) do handlers[k] = v end` (line 4882) picks it up
  automatically.
- **Modify:** `reaper_mcp/tools/fx_tools.py` — add the `fx_scan_params` MCP tool, wired to
  `plugin_cache` and `client.execute_long`.
- **Modify:** `docs/ARCHITECTURE.md` — add `fx_scan_params` to the tool list and note the new
  `plugin_maps/` cache directory in the file-layout section.

---

### Task 1: Constants and cache directory scaffolding

**Files:**
- Modify: `reaper_mcp_shared/constants.py`
- Create: `reaper_mcp_shared/plugin_maps/.gitkeep`
- Create: `reaper_mcp_shared/plugin_maps/README.md`
- Test: `tests/test_plugin_cache.py` (constants import check only in this task)

**Interfaces:**
- Produces: `reaper_mcp_shared.constants.PLUGIN_MAP_DIR` (str, absolute path), `reaper_mcp_shared.constants.MAX_SCAN_PARAMS` (int, 200).

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugin_cache.py` with just this first test:

```python
"""Tests for reaper_mcp_shared/plugin_cache.py — the VST param auto-scan cache.

Pure filesystem/string logic, no REAPER/IPC needed (mirrors test_command_history.py).
"""

import os

from reaper_mcp_shared.constants import PLUGIN_MAP_DIR, MAX_SCAN_PARAMS


class TestConstants:
    def test_plugin_map_dir_is_under_reaper_mcp_shared(self):
        assert os.path.basename(PLUGIN_MAP_DIR) == "plugin_maps"

    def test_max_scan_params_is_200(self):
        assert MAX_SCAN_PARAMS == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_plugin_cache.py -v`
Expected: FAIL with `ImportError: cannot import name 'PLUGIN_MAP_DIR'`

- [ ] **Step 3: Add the constants**

Open `reaper_mcp_shared/constants.py`. Add this near the top, after the `ALLOWED_EXPORT_FORMATS`
line (around line 76 in the current file):

```python
# Cache of scanned VST/AU parameter behavior (units, curve shape), keyed by
# plugin name. Deliberately NOT under Connection.IPC_DIR (private, 0700,
# per-machine) — these files are meant to be committed and shared, so a plain
# world-readable directory under the package is correct here.
PLUGIN_MAP_DIR = os.path.join(os.path.dirname(__file__), "plugin_maps")
MAX_SCAN_PARAMS = 200  # cap per fx_scan_params call — mirrors MAX_ANALYSIS_CANDIDATES's purpose
```

- [ ] **Step 4: Create the cache directory placeholder**

Create `reaper_mcp_shared/plugin_maps/.gitkeep` (empty file — makes the directory exist in git
before any real scan has been run and committed).

Create `reaper_mcp_shared/plugin_maps/README.md`:

```markdown
# Plugin parameter maps

Each file here is the cached result of `fx_scan_params` for one plugin: its parameter names,
three sampled display values (at 0%, 50%, 100%), and an inferred curve shape (`linear`,
`logarithmic`, `stepped`, or `unknown`). Generated automatically — don't hand-edit these unless
correcting a specific wrong inference. Filenames are the plugin's REAPER-reported name, sanitized
to lowercase alphanumerics with underscores.
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_plugin_cache.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add reaper_mcp_shared/constants.py reaper_mcp_shared/plugin_maps/.gitkeep reaper_mcp_shared/plugin_maps/README.md tests/test_plugin_cache.py
git commit -m "feat: add plugin param cache directory and constants"
```

---

### Task 2: `plugin_cache.py` — sanitize, infer_curve, load/save

**Files:**
- Create: `reaper_mcp_shared/plugin_cache.py`
- Test: `tests/test_plugin_cache.py` (append to the file from Task 1)

**Interfaces:**
- Consumes: `PLUGIN_MAP_DIR` (str), `MAX_SCAN_PARAMS` (int) from `reaper_mcp_shared.constants` (Task 1).
- Produces:
  - `sanitize_plugin_name(name: str) -> str`
  - `infer_curve(samples: list[str]) -> tuple[str, str | None]` — `(curve_type, unit)`, `curve_type` in `{"linear", "logarithmic", "stepped", "unknown"}`.
  - `load_cached_map(plugin_name: str) -> dict | None`
  - `save_cached_map(plugin_name: str, params: list[dict], truncated: bool) -> None`
  These four names and signatures are used as-is by Task 4 (`fx_tools.py`) — do not rename.

- [ ] **Step 1: Write failing tests for `sanitize_plugin_name`**

Append to `tests/test_plugin_cache.py`:

```python
from reaper_mcp_shared.plugin_cache import sanitize_plugin_name


class TestSanitizePluginName:
    def test_strips_punctuation_and_lowercases(self):
        assert sanitize_plugin_name("VST3: Pro-Q 3 (FabFilter)") == "vst3_pro_q_3_fabfilter"

    def test_collapses_repeated_separators(self):
        assert sanitize_plugin_name("A -- B") == "a_b"

    def test_no_leading_or_trailing_underscore(self):
        assert sanitize_plugin_name("  ReaEQ  ") == "reaeq"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_plugin_cache.py::TestSanitizePluginName -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reaper_mcp_shared.plugin_cache'`

- [ ] **Step 3: Implement `sanitize_plugin_name`**

Create `reaper_mcp_shared/plugin_cache.py`:

```python
"""VST/AU parameter auto-scan cache: infers each parameter's units and curve
shape from REAPER's own formatted display strings, and caches the result per
plugin so a plugin only ever needs to be scanned once (see fx_scan_params in
reaper_mcp/tools/fx_tools.py and the design doc at
docs/superpowers/specs/2026-08-06-vst-param-autoscan-design.md).
"""

import json
import os
import re
import time

from reaper_mcp_shared.constants import PLUGIN_MAP_DIR


def sanitize_plugin_name(name: str) -> str:
    """Turn a raw FX name like 'VST3: Pro-Q 3 (FabFilter)' into a safe filename stem."""
    safe = re.sub(r"[^A-Za-z0-9]+", "_", name.strip())
    return safe.strip("_").lower()
```

- [ ] **Step 4: Run to verify `sanitize_plugin_name` tests pass**

Run: `pytest tests/test_plugin_cache.py::TestSanitizePluginName -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Write failing tests for `infer_curve`**

Append to `tests/test_plugin_cache.py`:

```python
from reaper_mcp_shared.plugin_cache import infer_curve


class TestInferCurve:
    def test_logarithmic_frequency(self):
        curve, unit = infer_curve(["20 Hz", "632 Hz", "20 kHz"])
        assert curve == "logarithmic"
        assert unit == "Hz"

    def test_linear_percentage(self):
        curve, unit = infer_curve(["0 %", "50 %", "100 %"])
        assert curve == "linear"
        assert unit == "%"

    def test_linear_decibels_with_negative_values(self):
        curve, unit = infer_curve(["-24.0 dB", "-12.0 dB", "0.0 dB"])
        assert curve == "linear"
        assert unit == "dB"

    def test_stepped_enum_returns_stepped(self):
        curve, unit = infer_curve(["Off", "Low", "High"])
        assert curve == "stepped"
        assert unit is None

    def test_mixed_numeric_and_text_is_unknown(self):
        curve, unit = infer_curve(["0 %", "Bypass", "100 %"])
        assert curve == "unknown"

    def test_constant_value_is_unknown_not_a_crash(self):
        curve, unit = infer_curve(["0 dB", "0 dB", "0 dB"])
        assert curve == "unknown"
```

- [ ] **Step 6: Run to verify failure**

Run: `pytest tests/test_plugin_cache.py::TestInferCurve -v`
Expected: FAIL — `ImportError: cannot import name 'infer_curve'`

- [ ] **Step 7: Implement `infer_curve`**

Append to `reaper_mcp_shared/plugin_cache.py`:

```python
_NUMBER_RE = re.compile(r"\s*(-?\d+\.?\d*)\s*([a-zA-Z%]*)")
_UNIT_MULTIPLIERS = {"k": 1000.0, "m": 0.001}


def _parse_numeric(s: str):
    """Extract (number, unit) from a formatted display string, or (None, None)
    if it doesn't start with a number (e.g. 'Off', 'Bypass')."""
    m = _NUMBER_RE.match(s)
    if not m or not m.group(1):
        return None, None
    return float(m.group(1)), m.group(2)


def _normalize(num: float, unit: str):
    """Fold a k/m unit prefix into the number so '20 kHz' and '632 Hz' are comparable."""
    if unit and len(unit) > 1 and unit[0].lower() in _UNIT_MULTIPLIERS:
        return num * _UNIT_MULTIPLIERS[unit[0].lower()], unit[1:]
    return num, unit


def infer_curve(samples: list) -> tuple:
    """Infer a parameter's curve shape from 3 display strings sampled at
    normalized 0.0, 0.5, and 1.0.

    Returns (curve_type, unit) where curve_type is one of "linear",
    "logarithmic", "stepped", or "unknown". "unknown" is a valid, expected
    outcome (e.g. a constant-value param) — not an error.
    """
    parsed = [_parse_numeric(s) for s in samples]
    numeric_count = sum(1 for num, _ in parsed if num is not None)

    if numeric_count == 0:
        return "stepped", None
    if numeric_count < len(samples):
        return "unknown", None

    normalized = [_normalize(num, unit) for num, unit in parsed]
    values = [v for v, _ in normalized]
    units = [u for _, u in normalized]
    unit = units[0] if len(set(units)) == 1 else None

    v0, v1, v2 = values
    if v0 == v1 == v2:
        return "unknown", unit

    diff1 = v1 - v0
    diff2 = v2 - v1
    span = abs(v2 - v0) or 1.0

    if abs(diff1 - diff2) <= 0.15 * span:
        return "linear", unit

    if v0 != 0 and v1 != 0:
        ratio1 = v1 / v0
        ratio2 = v2 / v1
        if ratio1 > 0 and ratio2 > 0 and abs(ratio1 - ratio2) <= 0.15 * max(ratio1, ratio2):
            return "logarithmic", unit

    return "unknown", unit
```

- [ ] **Step 8: Run to verify `infer_curve` tests pass**

Run: `pytest tests/test_plugin_cache.py::TestInferCurve -v`
Expected: PASS (6 tests)

- [ ] **Step 9: Write failing tests for `save_cached_map` / `load_cached_map`**

Append to `tests/test_plugin_cache.py`:

```python
import pytest

from reaper_mcp_shared import constants as _constants
from reaper_mcp_shared.plugin_cache import load_cached_map, save_cached_map


@pytest.fixture
def plugin_map_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(_constants, "PLUGIN_MAP_DIR", str(tmp_path / "plugin_maps"))
    monkeypatch.setattr("reaper_mcp_shared.plugin_cache.PLUGIN_MAP_DIR", str(tmp_path / "plugin_maps"))
    return str(tmp_path / "plugin_maps")


class TestCacheRoundTrip:
    def test_save_then_load_returns_same_params(self, plugin_map_dir):
        params = [{"index": 0, "name": "Freq", "samples": ["20 Hz", "632 Hz", "20 kHz"],
                   "inferred_curve": "logarithmic", "inferred_unit": "Hz"}]
        save_cached_map("Test Plugin", params, truncated=False)

        loaded = load_cached_map("Test Plugin")
        assert loaded["plugin_name"] == "Test Plugin"
        assert loaded["truncated"] is False
        assert loaded["params"] == params
        assert "scanned_at" in loaded

    def test_load_missing_plugin_returns_none(self, plugin_map_dir):
        assert load_cached_map("Never Scanned Plugin") is None

    def test_load_corrupt_file_returns_none_not_raise(self, plugin_map_dir):
        os.makedirs(plugin_map_dir, exist_ok=True)
        from reaper_mcp_shared.plugin_cache import sanitize_plugin_name
        path = os.path.join(plugin_map_dir, sanitize_plugin_name("Broken") + ".json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        assert load_cached_map("Broken") is None

    def test_save_creates_directory_if_missing(self, plugin_map_dir):
        assert not os.path.isdir(plugin_map_dir)
        save_cached_map("Any Plugin", [], truncated=False)
        assert os.path.isdir(plugin_map_dir)
```

- [ ] **Step 10: Run to verify failure**

Run: `pytest tests/test_plugin_cache.py::TestCacheRoundTrip -v`
Expected: FAIL — `ImportError: cannot import name 'load_cached_map'`

- [ ] **Step 11: Implement `save_cached_map` and `load_cached_map`**

Append to `reaper_mcp_shared/plugin_cache.py`:

```python
def load_cached_map(plugin_name: str):
    """Return the cached scan for this plugin, or None if never scanned or corrupt."""
    path = os.path.join(PLUGIN_MAP_DIR, sanitize_plugin_name(plugin_name) + ".json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_cached_map(plugin_name: str, params: list, truncated: bool) -> None:
    """Write a scan result to the cache. Best-effort: a write failure here
    must never break the scan response the caller already has in hand."""
    try:
        os.makedirs(PLUGIN_MAP_DIR, exist_ok=True)
        record = {
            "plugin_name": plugin_name,
            "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "truncated": truncated,
            "params": params,
        }
        path = os.path.join(PLUGIN_MAP_DIR, sanitize_plugin_name(plugin_name) + ".json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass
```

- [ ] **Step 12: Run full test file to verify everything passes**

Run: `pytest tests/test_plugin_cache.py -v`
Expected: PASS (all tests: 2 constants + 3 sanitize + 6 infer_curve + 4 cache round-trip = 15 tests)

- [ ] **Step 13: Commit**

```bash
git add reaper_mcp_shared/plugin_cache.py tests/test_plugin_cache.py
git commit -m "feat: add plugin param cache module with curve inference"
```

---

### Task 3: Lua `fx_scan_params` handler

**Files:**
- Modify: `reaper_scripts/reaper_mcp_server.lua`

**Interfaces:**
- Consumes: `get_track(p)` (existing helper, returns `track, idx, err`), `math.floor` (builtin).
- Produces: command `fx_scan_params`, accepting `{track_index, fx_index, max_params}` and
  returning `{fx_name: string, truncated: bool, params: [{index: int, name: string, samples: [string, string, string]}]}`
  on success, or `(nil, error_string)` on failure. This exact shape is consumed by Task 4.

This handler cannot be unit tested (no existing Lua test harness in this repo — same boundary
every other `fx.*` handler already has). Verify manually in Step 2.

- [ ] **Step 1: Add the handler**

Open `reaper_scripts/reaper_mcp_server.lua`. Find `function fx.fx_set_param_by_name(p)` (around
line 1342) and insert this new function immediately after that function's closing `end`:

```lua
function fx.fx_scan_params(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  if not p.fx_index then return nil, "Missing parameter: fx_index" end
  local fi = math.floor(p.fx_index)
  local max_params = p.max_params or 200

  local num = reaper.TrackFX_GetNumParams(tr, fi)
  local truncated = false
  local limit = num
  if num > max_params then
    limit = max_params
    truncated = true
  end

  local params = {}
  local points = {0.0, 0.5, 1.0}
  for i = 0, limit - 1 do
    local _, pname = reaper.TrackFX_GetParamName(tr, fi, i, "")
    local orig_val = reaper.TrackFX_GetParam(tr, fi, i)
    local is_midi_cc = pname:find("^MIDI CC")
    local skip = (pname == "-" and orig_val == 0) or is_midi_cc
    if not skip then
      local samples = {}
      for _, pt in ipairs(points) do
        reaper.TrackFX_SetParam(tr, fi, i, pt)
        local val = reaper.TrackFX_GetParam(tr, fi, i)
        local _, fmt = reaper.TrackFX_FormatParamValue(tr, fi, i, val, "")
        samples[#samples + 1] = fmt
      end
      reaper.TrackFX_SetParam(tr, fi, i, orig_val)
      params[#params + 1] = {index = i, name = pname, samples = samples}
    end
  end

  local _, fx_name = reaper.TrackFX_GetFXName(tr, fi, "")
  return {fx_name = fx_name, truncated = truncated, params = params}
end
```

- [ ] **Step 2: Manually verify against real REAPER**

With REAPER open and the MCP server running:
1. Add ReaEQ to a track (a stock plugin every REAPER install has, so this step works for anyone
   following this plan).
2. Send a raw `fx_scan_params` command with `track_index` pointing at that track and `fx_index=0`
   (via whatever manual command-testing method the project already uses for Lua handlers — e.g. a
   scratch script or the existing `script_run` tool pointed at a one-off test script).
3. Confirm the response has a `params` array where each entry has 3 `samples` strings that look
   like real formatted values (e.g. gain/frequency numbers with units), and confirm ReaEQ's
   parameters are back to their original values afterward (check the plugin UI).

- [ ] **Step 3: Commit**

```bash
git add reaper_scripts/reaper_mcp_server.lua
git commit -m "feat: add fx_scan_params Lua handler"
```

---

### Task 4: Python `fx_scan_params` tool + docs

**Files:**
- Modify: `reaper_mcp/tools/fx_tools.py`
- Modify: `docs/ARCHITECTURE.md`

**Interfaces:**
- Consumes:
  - `reaper_mcp_shared.plugin_cache.load_cached_map`, `save_cached_map`, `infer_curve` (Task 2).
  - `reaper_mcp_shared.constants.MAX_SCAN_PARAMS` (Task 1).
  - `client.execute("fx_get_chain", track_index=...)` → `{"fx_chain": [{"name": str, ...}, ...], ...}` (existing).
  - `client.execute_long("fx_scan_params", track_index=..., fx_index=..., max_params=...)` → shape from Task 3.
- Produces: MCP tool `fx_scan_params(track_index: int, fx_index: int) -> dict`, returning
  `{"plugin_name": str, "truncated": bool, "params": [...], "from_cache": bool}`.

- [ ] **Step 1: Add the tool**

Open `reaper_mcp/tools/fx_tools.py`. Add this import near the top of the file, alongside the
existing imports:

```python
from reaper_mcp_shared.constants import MAX_SCAN_PARAMS
from reaper_mcp_shared.plugin_cache import infer_curve, load_cached_map, save_cached_map
```

Add this tool inside `register(mcp)`, after `fx_set_param_by_name` (so it sits with the other
param-level tools):

```python
    @mcp.tool()
    async def fx_scan_params(track_index: int, fx_index: int) -> dict:
        """Scan an FX plugin's parameters to learn their range/units/curve shape.

        Sweeps each parameter through its range once and caches the result by
        plugin name, so repeat scans of the same plugin (even in a different
        project) return instantly from the on-disk cache instead of touching
        REAPER again. This is a deliberately separate, explicit tool from
        fx_get_params — it briefly writes and restores every parameter's
        value and can take longer on plugins with many parameters, so call
        it when you need to understand an unfamiliar plugin's behavior, not
        as part of routine reads.

        Args:
            track_index: 0-based track index.
            fx_index: 0-based FX chain index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if fx_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "fx_index must be >= 0")

        chain = await client.execute("fx_get_chain", track_index=track_index)
        fx_list = chain.get("fx_chain", [])
        if not 0 <= fx_index < len(fx_list):
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "fx_index out of range for this track")
        plugin_name = fx_list[fx_index]["name"]

        cached = load_cached_map(plugin_name)
        if cached is not None:
            return {**cached, "from_cache": True}

        result = await client.execute_long(
            "fx_scan_params", track_index=track_index, fx_index=fx_index, max_params=MAX_SCAN_PARAMS,
        )
        params = []
        for entry in result.get("params", []):
            curve, unit = infer_curve(entry["samples"])
            params.append({
                "index": entry["index"],
                "name": entry["name"],
                "samples": entry["samples"],
                "inferred_curve": curve,
                "inferred_unit": unit,
            })
        truncated = bool(result.get("truncated", False))
        save_cached_map(plugin_name, params, truncated)
        return {
            "plugin_name": plugin_name,
            "truncated": truncated,
            "params": params,
            "from_cache": False,
        }
```

- [ ] **Step 2: Manually verify the full round trip**

With REAPER open and the MCP server running, call `fx_scan_params` (via Claude Desktop/Code or a
manual MCP client) on a track with ReaEQ loaded. Confirm:
1. First call: `from_cache` is `false`, response includes inferred curves, and
   `reaper_mcp_shared/plugin_maps/reaeq.json` now exists on disk.
2. Second call on the same plugin: `from_cache` is `true` and the response returns near-instantly
   (no REAPER round trip — you can verify this by disabling/closing REAPER after the first call
   and confirming the second call still succeeds).

- [ ] **Step 3: Update ARCHITECTURE.md**

Open `docs/ARCHITECTURE.md`. In the tool list section, add `fx_scan_params` alongside the other
`fx_*` tools. In the file-layout / IPC files section, add a row for
`reaper_mcp_shared/plugin_maps/*.json` describing it as the committable, shared VST parameter
cache (distinct from the private `history/*.json` files — this one is meant to be checked into
git).

- [ ] **Step 4: Run the full test suite**

Run: `pytest -v`
Expected: PASS, no regressions (should be the prior total + the 15 new tests from Task 2).

- [ ] **Step 5: Commit**

```bash
git add reaper_mcp/tools/fx_tools.py docs/ARCHITECTURE.md
git commit -m "feat: add fx_scan_params MCP tool with on-disk plugin cache"
```

---

## Plan Self-Review Notes

- **Spec coverage:** Motivation → Task 2 (`infer_curve` replaces hand-curation). Architecture →
  Tasks 2-4 map 1:1 to the spec's Lua/Python/module/directory split. Trigger mechanism (explicit
  tool only) → Task 4, no changes to any existing tool. Data flow steps 1-8 → Task 4 Step 1
  line-by-line. Cache file format → Task 2 `save_cached_map` matches the spec's JSON shape exactly
  (`plugin_name`, `scanned_at`, `truncated`, `params`). Error handling (cap, restore-on-failure,
  best-effort write, timeout) → Task 3 (cap, restore) and Task 2/4 (best-effort write,
  `execute_long`). Testing section → Tasks 2 and 4 Step 4.
- **Type consistency checked:** `infer_curve` returns `(curve_type, unit)` consistently used in
  Task 4 as `curve, unit = infer_curve(...)`. `load_cached_map`/`save_cached_map` signatures match
  between Task 2's definition and Task 4's usage. The Lua response shape (`fx_name`, `truncated`,
  `params` with `index`/`name`/`samples`) matches exactly what Task 4 Step 1 reads via
  `result.get("params", [])` and `entry["samples"]`.
- **No placeholders:** every step above has real, complete code — no "add appropriate handling" or
  "similar to Task N" left unexpanded.
