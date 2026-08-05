# VST Parameter Auto-Scan & Cache — Design

## Motivation

Every existing FX param tool (`fx_get_params`, `fx_set_param`, `fx_set_param_by_name`) already
returns a human-readable `display` string per parameter via `TrackFX_FormatParamValue` — the AI
can already see that a param currently reads "1.2 kHz" or "-6.0 dB". What it can't do is learn a
parameter's *behavior* — its full range, units, and whether it's linear, logarithmic, or a stepped
enum — without guessing and checking live, one write at a time.

Hand-curating this per plugin (the current FabFilter approach, kept as domain knowledge rather than
a data file in this repo) doesn't scale — there are thousands of VST/AU plugins in the wild. This
feature replaces hand-curation with a one-time, cacheable scan: sweep a plugin's parameters once,
learn their shape from the plugin's own formatted output, and cache the result so every future
session — even in a different project — already knows the plugin.

## Non-goals (out of scope for this version)

- No GUI-only / non-automatable plugin state (preset browsers, custom toggles not exposed as
  automation params) — same limitation manual automation already has today.
- No automatic version-drift detection if REAPER can't expose a clean plugin version string; the
  cache entry carries a `scanned_at` timestamp so staleness is at least visible, not silently
  trusted forever, but there's no automatic invalidation.
- No full chunked/paginated scanning for extreme param counts — a simple cap (see Error Handling)
  covers this instead.

## Architecture

- **Lua side** (`reaper_scripts/reaper_mcp_server.lua`): new command handler `fx_scan_params`.
  Given a track/fx index, loops every parameter, skips the same "junk" params `build_fx_params`
  already skips (unnamed `-` params, `MIDI CC*` params), and for each remaining param sweeps 3
  sample points (0.0 / 0.5 / 1.0 normalized), reading the plugin's own formatted string at each
  point via `TrackFX_FormatParamValue`, then restores the original value. All of this happens
  inside **one** Lua command handler — one Python↔Lua IPC round trip total, regardless of param
  count, since the loop runs natively inside REAPER rather than being orchestrated call-by-call
  from Python.
- **Python side** (`reaper_mcp/tools/fx_tools.py`): new tool `fx_scan_params(track_index, fx_index)`.
  Checks the on-disk cache first; only calls the Lua command on a cache miss. Infers each param's
  curve type from the 3 sampled display strings and writes the cache entry.
- **New module** `reaper_mcp_shared/plugin_cache.py`: load/save helpers for the cache, using the
  same atomic-write pattern (`.tmp` + `os.replace`) already used for command history.
- **New data directory** `reaper_mcp_shared/plugin_maps/*.json`: one file per plugin. Plain git-
  trackable JSON, intended to be committed and shared — this is a deliberate change from the
  private, per-machine `Connection.IPC_DIR` used for command history; plugin maps aren't secrets
  or session state, they're reusable knowledge worth distributing with the repo.

## Trigger mechanism

Explicit tool call only (`fx_scan_params`), not automatic/implicit scanning inside existing param
calls. Every existing tool's behavior and latency stays exactly as it is today — nothing gets
slower or silently writes to a live parameter as a side effect of a normal read. The AI decides
when a deep scan is worth the cost, the same way it already decides when to reach for a heavier
tool like `setup_fx_chain` instead of a single `fx_set_param` call.

## Data flow

1. AI calls `fx_scan_params(track_index, fx_index)`.
2. Python resolves the FX name (existing call) and sanitizes it into a cache filename.
3. **Cache hit** → load the JSON file, return it. No REAPER round trip at all.
4. **Cache miss** → one IPC call to the new Lua `fx_scan_params` handler.
5. Lua returns raw per-param samples: `{index, name, samples: ["<display@0.0>", "<display@0.5>", "<display@1.0>"]}`.
6. Python infers curve type per param from the 3 strings (e.g. "20 Hz" / "632 Hz" / "20 kHz" →
   logarithmic frequency; "0%" / "50%" / "100%" → linear; repeated/non-numeric strings → stepped
   enum) and assembles the cache entry.
7. Python writes the cache file atomically.
8. Returns the full map to the AI.

## Cache file format

One file per plugin at `reaper_mcp_shared/plugin_maps/<sanitized_plugin_name>.json`:

```json
{
  "plugin_name": "VST3: Pro-Q 3 (FabFilter)",
  "scanned_at": "2026-08-06T00:00:00",
  "truncated": false,
  "params": [
    {
      "index": 0,
      "name": "Band 1 Frequency",
      "samples": ["20 Hz", "632 Hz", "20 kHz"],
      "inferred_curve": "logarithmic",
      "inferred_unit": "Hz"
    }
  ]
}
```

`inferred_curve` is one of `linear`, `logarithmic`, `stepped`, or `unknown` (when the 3 samples
don't clearly indicate a shape — this is a valid, expected outcome, not an error).

## Error handling

- **Param-count cap**: reuses the existing `MAX_ANALYSIS_CANDIDATES`-style pattern in
  `reaper_mcp_shared/constants.py` — plugins with very large param counts (some synths have
  100+) get truncated with `truncated: true` in the response rather than one huge blocking scan.
- **Restore-on-failure**: each param's sweep restores its original value immediately after
  sampling it, before moving to the next param — sequential and simple, no param is left mid-sweep
  if something goes wrong partway through.
- **Cache write is best-effort**: broad `except Exception: pass` around the write, matching the
  existing `_archive_command` pattern — a cache-write failure (e.g. disk full, bad path) must never
  break the actual scan response being returned to the AI.
- **Timeout**: `fx_scan_params` uses `Timeouts.LONG_COMMAND` (600s), not the default 30s
  `Timeouts.COMMAND` — a param-heavy plugin doing dozens of sequential sweep-and-restore cycles
  inside one Lua call is the same shape of long-running batch operation as MIDI/FX batch writes,
  which already use the longer timeout.

## Testing

- **Pure-logic unit tests** (no REAPER needed) for the curve-inference function in
  `reaper_mcp_shared/plugin_cache.py` — feed fake sample-string triples, assert the inferred curve
  type. Same style as the existing `test_command_history.py`.
- **Cache read/write tests** via `tmp_path`, verifying: a cache hit returns without invoking the
  Lua call path, the atomic write pattern holds, and a corrupt/missing cache file is treated as a
  miss rather than raising.
- **Truncation test**: a plugin with a param count above the cap returns `truncated: true` and a
  capped param list.
- The Lua-side sweep itself is not unit-testable — same boundary every existing Lua command in
  this repo already has. Verified manually against a real REAPER instance with a real plugin
  loaded, consistent with how the rest of the codebase handles this split between Python-testable
  logic and Lua-side REAPER interaction.

## Open items to verify during implementation

- Whether REAPER's ReaScript API exposes a clean, stable plugin version string for use in the
  cache key. If not, the cache stays keyed by plugin name only, relying on `scanned_at` for
  staleness visibility rather than automatic invalidation.
