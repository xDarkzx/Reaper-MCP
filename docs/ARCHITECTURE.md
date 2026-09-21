# Architecture

How ReaperMCP connects an AI client to REAPER, how tools are discovered and dispatched, and how the mix engine translates a style name into a full mixing + mastering session.

---

## Overview

```
┌──────────────┐    stdio    ┌──────────────┐   file IPC    ┌──────────────┐
│  MCP Client  │◄──────────►│  ReaperMCP   │◄────────────►│    REAPER    │
│(AI assistant)│  (JSON-RPC) │   FastMCP    │  (JSON files) │  (Lua script)│
└──────────────┘             └──────────────┘               └──────────────┘
```

Three processes, two transports:

1. The **MCP client** (Claude Desktop, Claude Code, Cursor, …) speaks [Model Context Protocol](https://modelcontextprotocol.io) over stdio.
2. The **Python server** (`reaper-mcp`) is a [FastMCP](https://github.com/jlowin/fastmcp) app that translates MCP tool calls into structured commands.
3. A **Lua script** running inside REAPER receives each command via a shared temp-dir, executes it against REAPER's scripting API, and writes the response back.

No sockets, no ports, no network exposure.

---

## The Lua ↔ Python IPC protocol

The Python server and the Lua bridge communicate through four files in a shared directory:

| File | Written by | Purpose |
|------|-----------|---------|
| `server.lock` | Lua | Heartbeat — mtime is refreshed every tick. Absence → REAPER isn't running. Staler than 60 s → REAPER froze. |
| `command.json` | Python | Next command to execute. Atomic-write via `command.tmp` → `os.replace`. |
| `response.json` | Lua | Result of the last command. Python deletes it after reading. |
| `command.tmp` / `response.tmp` | both | Stage files so readers never see a half-written payload. |
| `history/*.json` | Python | One file per completed command (pass or fail) — see request lifecycle step 8. Not part of the live protocol, purely an after-the-fact audit trail. |

Note: `reaper_mcp_shared/plugin_maps/*.json` (the `fx_scan_params` cache) is a different kind of
file entirely — it lives in the package itself, not this shared temp directory, and is meant to be
committed to git and shared between users, unlike everything in the table above which is private
and per-machine.

`fx_scan_params` itself is an on-demand fallback, not an automated or proactive tool — it's not
called as part of any other tool's normal flow, and the AI is only expected to reach for it when
genuinely unsure of a specific parameter's real range/units, not to "get to know" a plugin in
general. See the tool's own docstring and
`docs/superpowers/specs/2026-08-06-vst-param-autoscan-design.md` for the full reasoning: scanning
only solves parameter *calibration*, not plugin or parameter *semantics*, and semantics turned out
to be the more important and more common problem to solve for well-documented professional
plugins — which reasoning already handles without this tool.

Paths:

- **Windows:** `%TEMP%\reaper_mcp` (e.g., `C:\Users\You\AppData\Local\Temp\reaper_mcp`)
- **macOS:** `$TMPDIR/reaper_mcp` (usually `/var/folders/.../T/reaper_mcp`)
- **Linux:** `/tmp/reaper_mcp`

Both sides resolve the directory through Python's `tempfile.gettempdir()` and Lua's `os.getenv("TMPDIR")` with platform fallbacks, so the Python server and the Lua script always agree.

### Request lifecycle

1. Python calls `ReaperClient.execute("my_command", **params)`.
2. The client checks the lock file heartbeat; if stale, it raises `CONNECTION_LOST` before issuing the command.
3. Old command/response files are cleaned up.
4. The command is written to `command.tmp`, then atomically renamed to `command.json`.
5. The client polls for `response.json` every 50 ms, up to the command timeout (30 s normally, 600 s for bulk MIDI / FX writes) — re-checking heartbeat staleness roughly every 2 s during the wait, so a REAPER crash mid-command surfaces well before the full timeout rather than only being caught by step 2's pre-flight check.
6. The Lua script sees the new `command.json`, dispatches to the named handler, and writes the result.
7. Python reads the response, deletes it, and returns.
8. Regardless of outcome, a small record (command, params preview, pass/fail, duration) is archived to `history/` as its own JSON file, since `command.json`/`response.json` themselves are deleted the moment the round-trip finishes — without this there would be no record of what was sent once a command completes. Swept for entries older than 30 days (`HISTORY_RETENTION_DAYS`) on server startup and probabilistically (1 in 200) on each new command, so a long-running server doesn't need a dedicated timer to eventually clean up. Best-effort — archiving failures are swallowed, never propagated to the caller.

Errors and malformed responses trigger typed errors (`ReaperMCPError` with an `ErrorCode`) — never a silent hang.

### Safety limits

From `reaper_mcp_shared/constants.py`:

- `MAX_COMPOSE_TRACKS = 50` — per `compose_arrangement` / `configure_tracks` call.
- `MAX_NOTES_PER_TRACK = 10 000`, `MAX_TOTAL_NOTES_PER_CALL = 50 000` — cap single-batch MIDI writes to keep REAPER responsive.
- `MAX_ANALYSIS_CANDIDATES = 300` (whole-file), `MAX_ANALYSIS_CANDIDATES_PER_REGION = 50` — cap `analyze_silence`/`analyze_peaks`/`analyze_region_qc` candidate lists; a busy or noisy file can produce far more raw detections than anyone would review.
- `HISTORY_RETENTION_DAYS = 30`, `HISTORY_PARAM_PREVIEW_CHARS = 2000` — command-history entries are deleted after 30 days; each entry's stored params/result are capped so one huge batch call doesn't turn the history directory into its own version of the data-dump problem.
- Allowed export formats: `wav`, `mp3`, `ogg`, `flac`, `aiff`.

Read-side lookups (individual track/item/FX operations by index) rely on REAPER's own API returning a null handle for an out-of-range index — each handler checks for that and errors cleanly, so there's no separate ceiling constant needed there.

These are intentionally conservative — REAPER's main thread blocks while Lua parses a large JSON payload, so huge calls would stall playback.

---

## Dynamic tool registration

`reaper_mcp/tool_registry.py` walks every Python module under `reaper_mcp/tools/` with `pkgutil.iter_modules`. Any module that defines `register(mcp: FastMCP)` is considered a tool provider and gets its `register(...)` called once at startup.

```python
# reaper_mcp/tools/my_tools.py
def register(mcp):
    @mcp.tool()
    async def my_tool(param: float = 1.0) -> dict:
        return await client.execute("MyCommand", param=param)
```

That's it — the file is auto-discovered on the next server start.

### Filtering, Allowlists, and Instructions

When tools are registered, `register_all_tools(mcp, profile)` passes a `ToolFilterProxy` wrapping FastMCP. This proxy dynamically filters tool registrations against the active `ToolProfile`:
- **Module-level filtering:** Skips excluded or non-included modules before importing or registering.
- **Exact tool-level filtering:** Intercepts `@mcp.tool()` to filter by tool name (`include_tools`, `exclude_tools`).
- **Profile-scoped instructions:** `load_instructions(profile.instruction_packs)` composes only the relevant markdown packs from `reaper_mcp/instructions/` (cutting context size by up to ~85% for narrow profiles while keeping safety rules intact).
- **Introspection:** `describe_profile(...)` provides exact measurements of tool counts, schema sizes, and instruction sizes.

If a module raises during import or registration, the registry logs the failure, writes a visible banner to stderr, and continues loading the rest. One broken file can't take the server down.

Modules without a `register(...)` function (e.g., `compose_helpers.py`) are silently skipped, so helper modules can live in the same folder without being mistaken for tool providers.

---

## The Lua bridge

`reaper_scripts/reaper_mcp_server.lua` is ~5 500 lines and runs as a deferred ReaScript (i.e., REAPER calls its main function on every UI tick). Each tick it:

1. Refreshes the lock file mtime (heartbeat).
2. Checks for `command.json`. If present, parses and dispatches.
3. Writes the result through `response.tmp` → atomic rename to `response.json`.

Every handler is a static function keyed by name in a dispatch table — **no `dofile`, no `load`, no `loadstring`**. That means every command corresponds to explicit, reviewable Lua code with input validation per handler.

The bridge is cross-platform: it detects OS via `reaper.GetOS()` and picks the right temp directory without the Python side having to tell it.

### Failure containment

Every command runs under `pcall`, so an error in a handler returns an error response instead of stopping the bridge. Two REAPER states can outlive a throw, though: a `PreventUIRefresh` hold (the UI stays frozen) and an open undo block. Handlers close both on their last lines, which a throw skips.

`install_block_guard` wraps `PreventUIRefresh`, `Undo_BeginBlock` and `Undo_EndBlock` once at startup. The wrapper only counts and passes every argument and return value through. After each command, whatever its outcome and before any response is written, the dispatcher calls the returned unwind function, which releases any refresh hold and ends any open undo block. Ending the block records the partial work as one undo point, so it can still be undone. When something had to be unwound, the bridge notes it in REAPER's console. Handlers need no per-handler `pcall` for this, and new handlers are covered automatically (`tests/test_lua_block_guard.py`).

### Undo

Every change made through the bridge is one named undo step, so a mistake can be reversed with one undo (`project_undo`, or Ctrl+Z in REAPER).

- **Track, FX and routing batch handlers** (`track_create`, `track_delete_batch`, `fx_remove_batch`, `setup_fx_chain`, `setup_master_chain`, `setup_effect_bus`, `setup_sidechain`, `setup_routing`, `configure_tracks`) wrap their work in their own `Undo_BeginBlock` / `Undo_EndBlock`, so a whole call collapses into one step.
- **Everything else that changes the project** is listed in `UNDO_POINT_COMMANDS` (75 commands): simple edits such as a fader, pan, send, marker or tempo change, and every handler that touches items, MIDI notes or takes. After such a command succeeds, the dispatcher records one step named `MCP: <command>` (or the descriptive name the handler asked for, like `MCP: midi_insert_notes_batch (4 notes)`). Failed commands leave no step, and recording is best effort, so it can never fail a command.

**Why items and MIDI are recorded by the dispatcher, not by a block.** REAPER's undo blocks do not capture MIDI item, note and take data when they are called from the bridge: the step they leave is empty or missing, so undoing it restores nothing (found by live testing, where undoing `item_create_midi` left the item in place). REAPER's two state-change calls each cover what the other misses: `Undo_OnStateChange2` records items, MIDI and takes, and the flagged `Undo_OnStateChangeEx2` records everything else (track, FX, send, marker, tempo). `record_undo_step` uses **exactly one** of them per command, chosen by what the command changes: the commands in `UNDO_ITEM_COMMANDS` use `Undo_OnStateChange2`, and every other recorded command uses the flagged call. Calling both for one command is not an option, because REAPER syncs item state lazily and a tool that sends commands back to back sometimes recorded an item change twice. The one exception is `track_set_state_chunk`, which replaces a whole track including its items, so it makes both calls. For the commands in `UNDO_POINT_COMMANDS` the block guard keeps a handler's own `Undo_BeginBlock` / `Undo_EndBlock` out of REAPER and only remembers the name the handler asked for, so a command never leaves an extra empty step.
- **Exempt commands** (`UNDO_EXEMPT_COMMANDS`, each with a reason) get no step: read-only calls, transport and selection, file operations and renders, REAPER actions that record their own step, and undo and redo themselves. Recording a point after an undo would erase the redo stack.

Every handler that changes REAPER state must be in exactly one of the two tables (or manage its own block), and `tests/test_lua_undo_points.py` fails when a new handler is added without a decision, or when a handler that changes items or MIDI is left to an undo block.

**Undo groups.** A tool that runs several bridge commands, such as `engine_mix`, leaves one undo step per command, so a mistake can be undone piece by piece. Those tools are wrapped with `@undo_grouped(client, "<tool>")` (`reaper_mcp/undo_group.py`), which sends `undo_group_begin` first and `undo_group_end` last. While a group is open the bridge labels every step it records `MCP: <tool>#<run> > <command>` (for example `MCP: engine_mix#7 > setup_fx_chain`), where the run number tells two runs of the same tool apart. Two tools use that label:

- `project_undo(steps=N)` undoes the last N steps in one call, so the last two or three commands of a ten-command tool can be taken back without touching the rest.
- `project_undo_group` undoes every consecutive step of the most recent run, stopping at the first step that belongs to something else.

A group only labels; it holds nothing open in REAPER. That is deliberate: REAPER drops an undo block that is held open between bridge ticks, so collapsing a whole tool into one step is not possible, and it would also have taken away the finer control. Groups nest (an inner tool joins the outer run), the group is closed even if the tool raises, and an older bridge script that doesn't know the commands just leaves the tool unlabelled. If a caller never closes its group (the Python process died), the bridge stops labelling after 60 seconds without a command and says so in REAPER's console. The wrapped tools are listed in `tests/test_undo_group.py`, which fails if one loses its decorator.

### Track addressing and the master track

REAPER keeps the master track outside its numbered track list: `GetTrack(0, i)` never returns it, `GetMasterTrack(0)` does. The bridge exposes it as `track_index = -1`, resolved in one place:

- **`get_track(params, key)`** — the standard lookup used by most handlers. Resolves `-1` to the master track, any other index to a numbered track.
- **`get_numbered_track(params, key)`** — `get_track` that refuses `-1`. Used by handlers where the master track is meaningless or dangerous: `track_delete_batch` (for each target it resolves), `track_freeze`, `track_unfreeze`, `track_set_folder`, `track_set_input`, `track_set_record_arm` and `track_set_state_chunk`.
- **`batch_track_from_index(ti)`** — the same `-1` rule for the batch entry points (`setup_fx_chain`, `configure_tracks`) that receive a raw index per entry instead of a params table.

Which tools accept `-1` is therefore decided twice: the Python tool validates first, and the Lua handler enforces it again. A destructive handler keeps refusing the master even if a Python guard is later loosened. New handlers that act on a track should use `get_numbered_track` unless acting on the master is meaningful. The behaviour of both lookups is tested by running the real Lua helpers under `lupa` with a stubbed `reaper` (`tests/test_lua_master_guard.py`).

---

## Mix engine

The mix engine turns a single style name (e.g., `melodic_dubstep`) into a fully routed and processed mixing session, then optionally a master bus chain. It lives under `reaper_mcp/mix_engine/`.

### Pipeline

`run_mix_pipeline(client, track_map, style, clean)` executes six phases:

1. **Detect** — probe the installed plugin set to decide whether to use FabFilter (Pro-Q 3 / Pro-C 2 / Pro-R) or REAPER stock (ReaEQ / ReaComp / ReaVerbate). See `detect.py` and `fx_inventory.py`.
2. **Clean** — if `clean=True`, strip any previously-added mix FX and delete mix-engine-created bus tracks (prefixed `MIX:`). Named in `_MIX_EQ_NAMES`, `_MIX_COMPRESSOR_NAMES`, `_MIX_REVERB_NAMES`.
3. **Volume staging** — set a reasonable initial fader for each role (kick a few dB under lead vocal, bass below kick, pads well below …).
4. **Per-track EQ** — high-pass filters, surgical cuts, tonal shaping driven by the style's role profile.
5. **Per-track compression** — attack / release / ratio / threshold from the role profile.
6. **Reverb bus routing** — up to three buses (Hall / Room / Plate) with per-role sends.

The master chain (`run_master_pipeline`) is independent and can be run standalone via `engine_master(style)`: HP 25 Hz → bus glue comp → tonal shelf EQ → stereo width → brick-wall limiter with style-specific LUFS and true-peak targets.

### Style profile catalog

`reaper_mcp/mix_engine/catalog/` is organised by family:

```
catalog/
├── _shared.py       # Role → EQ/comp library shared by every family
├── edm.py           # 11 EDM subgenres
├── rock.py          # 6 rock subgenres
├── pop.py           # 4 pop subgenres
├── electronic.py    # synthwave, lofi, ambient, hiphop
├── jazz.py          # swing_jazz, jazz_fusion, latin_jazz
├── orchestral.py    # classical_chamber, cinematic_trailer, ambient_orchestral
└── funk_soul.py     # classic_funk, motown_soul, neo_soul, disco_funk
```

Each family registers its profiles into a central registry at import time. Adding a new style is: drop a profile dict into the relevant family file, name the track roles it expects, pick the reverb buses it wants — no pipeline changes.

When a style **isn't** in the v2 catalog, the engine falls back to the legacy orchestral path in `profiles.py`, which matches against VSTi names (Spitfire Violin 1, BBC Brass, …) instead of track names.

**Two orchestral paths, deliberately** — `catalog/orchestral.py`'s v2 styles
(`classical_chamber`/`cinematic_trailer`/`ambient_orchestral`) use consolidated
section roles (`strings_section`, `brass_orchestral`, `woodwinds`, `choir`) for
projects with one track per section. `profiles.py`'s legacy path has
per-instrument tuning (separate `violin_1`/`violin_2`/`viola`/`cello`, each
individual woodwind/brass) for a full multi-mic orchestral template — that's
the finer-grained option and is what you get from any style name not in the
v2 catalog (empty string included). Don't consolidate `profiles.py` into the
v2 catalog format — the per-instrument granularity is the point.

### Role resolution

v2 style profiles don't hard-code track indices. They describe **roles** — "lead vocal", "kick", "808 bass", "stacks". At runtime, `mix_engine` walks the live track list and matches each track's name against alias tables defined in `_shared.py`.

That means the same style profile works regardless of whether you named your kick track "Kick", "KICK 01", or "Drum - Kick Main".

### Plugin parameter translation

`plugins.py` holds a tightly calibrated param-name mapping for FabFilter Pro-Q 3 / Pro-C 2 / Pro-R and REAPER stock. For other brands (Waves, iZotope, Valhalla, Softube …) the engine adds the plugin but uses fuzzy name matching — approximate, works for most cases, and the user is told to fine-tune afterwards.

Users can pin category → plugin preferences via `set_fx_preferences({"eq": "...", "compressor": "..."})`. Stored at `%APPDATA%/reaper_mcp/fx_prefs.json` on Windows and `~/.config/reaper_mcp/` on macOS / Linux.

---

## Package layout

```
reaper_mcp/
├── main.py                 # FastMCP entry point — `reaper-mcp` command
├── tool_registry.py        # Auto-discovers tool modules
├── reaper_client.py        # File-IPC client (+ async lock, heartbeat, timeouts)
├── cc_map.py               # CC number translation helpers
├── shorthand.py            # Compact composition notation parser
├── instructions/
│   └── 00_core.md          # System-prompt instructions injected into the MCP
│                           #   server's `instructions` field (composition workflow,
│                           #   BBC Spitfire CC reference, style cheat sheet).
├── tools/                  # 26 modules, 181 tools (auto-registered)
└── mix_engine/             # Detect → clean → EQ → comp → reverb → master pipeline

reaper_mcp_shared/
├── constants.py            # IPC paths, timeouts, safety limits
├── error_codes.py          # Typed error codes (ReaperMCPError + ErrorCode enum)
├── protocol.py             # Command / response formatting helpers
├── plugin_cache.py         # fx_scan_params cache: curve inference, load/save
└── plugin_maps/            # Cached VST/AU param scans, one JSON file per plugin —
                             #   git-tracked and shareable, NOT the private IPC dir

reaper_scripts/
└── reaper_mcp_server.lua   # Lua IPC bridge (runs inside REAPER)

docs/
├── INSTALLATION.md         # Platform-specific setup
├── PROJECT_SETUP.md        # VST templates for orchestral / pop / EDM
├── TOOLS.md                # Complete tool reference
└── ARCHITECTURE.md         # This file
```

---

## Design decisions

- **File-based IPC, not sockets.** No ports to allocate, no firewall surface, no network exposure. Works identically across every OS REAPER runs on.
- **Static dispatch, zero dynamic code.** The Lua bridge never executes arbitrary strings. Every handler is reviewable code with its own input validation.
- **Auto-registration of tools.** A contributor adds a file, exports `register(mcp)`, and the tool appears — no central registry to edit.
- **Fail loud on import errors, stay up.** One broken tool module never takes the whole server down.
- **Typed errors with cleanup.** `ReaperMCPError` + `ErrorCode` give the client specific, machine-readable failure reasons; malformed responses trigger retries bounded by `max_parse_failures` before surfacing.
- **Conservative single-call limits.** `MAX_TOTAL_NOTES_PER_CALL` and `MAX_COMPOSE_TRACKS` keep any one command under ~2 s of REAPER's main thread time on typical hardware.

See [TOOLS.md](TOOLS.md) for every tool grouped by domain, or [CONTRIBUTING.md](../CONTRIBUTING.md) for how to add more.
