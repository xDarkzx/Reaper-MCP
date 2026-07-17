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
5. The client polls for `response.json` every 50 ms, up to the command timeout (30 s normally, 600 s for bulk MIDI / FX writes).
6. The Lua script sees the new `command.json`, dispatches to the named handler, and writes the result.
7. Python reads the response, deletes it, and returns.

Errors and malformed responses trigger typed errors (`ReaperMCPError` with an `ErrorCode`) — never a silent hang.

### Safety limits

From `reaper_mcp_shared/constants.py`:

- `MAX_TRACKS = 500` — upper bound on any track index validation.
- `MAX_COMPOSE_TRACKS = 50` — per `compose_arrangement` / `configure_tracks` call.
- `MAX_NOTES_PER_TRACK = 10 000`, `MAX_TOTAL_NOTES_PER_CALL = 50 000` — cap single-batch MIDI writes to keep REAPER responsive.
- Allowed export formats: `wav`, `mp3`, `ogg`, `flac`, `aiff`.

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

If a module raises during import or registration, the registry logs the failure, writes a visible banner to stderr, and continues loading the rest. One broken file can't take the server down.

Modules without a `register(...)` function (e.g., `compose_helpers.py`) are silently skipped, so helper modules can live in the same folder without being mistaken for tool providers.

---

## The Lua bridge

`reaper_scripts/reaper_mcp_server.lua` is ~3 600 lines and runs as a deferred ReaScript (i.e., REAPER calls its main function on every UI tick). Each tick it:

1. Refreshes the lock file mtime (heartbeat).
2. Checks for `command.json`. If present, parses and dispatches.
3. Writes the result through `response.tmp` → atomic rename to `response.json`.

Every handler is a static function keyed by name in a dispatch table — **no `dofile`, no `load`, no `loadstring`**. That means every command corresponds to explicit, reviewable Lua code with input validation per handler.

The bridge is cross-platform: it detects OS via `reaper.GetOS()` and picks the right temp directory without the Python side having to tell it.

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
└── electronic.py    # synthwave, lofi, ambient, hiphop
```

Each family registers its profiles into a central registry at import time. Adding a new style is: drop a profile dict into the relevant family file, name the track roles it expects, pick the reverb buses it wants — no pipeline changes.

When a style **isn't** in the v2 catalog, the engine falls back to the legacy orchestral path in `profiles.py`, which matches against VSTi names (Spitfire Violin 1, BBC Brass, …) instead of track names.

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
├── tools/                  # 25 modules, 163 tools (auto-registered)
└── mix_engine/             # Detect → clean → EQ → comp → reverb → master pipeline

reaper_mcp_shared/
├── constants.py            # IPC paths, timeouts, safety limits
├── error_codes.py          # Typed error codes (ReaperMCPError + ErrorCode enum)
└── protocol.py             # Command / response formatting helpers

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
