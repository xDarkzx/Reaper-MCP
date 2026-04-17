# Installation Guide

Get ReaperMCP running in 3 steps: **install ReaperMCP → load the Lua script in REAPER → connect your AI client**.

---

## Step 1: Install ReaperMCP

### Option A: One-click installer (easiest)

- **Windows:** Double-click `install.bat` in the repo folder
- **macOS / Linux:** Open terminal in the repo folder and run `bash install.sh`

The installer handles Steps 1 and 3 for you — skip to [Load the Lua Script](#step-2-load-the-lua-script-in-reaper).

### Option B: pip install from source

```bash
cd Reaper-MCP
pip install -e .
```

This gives you the `reaper-mcp` command.

### Option C: Run directly (no install)

```bash
cd Reaper-MCP
python -m reaper_mcp.main
```

When running directly, use `python -m reaper_mcp.main` anywhere this guide says `reaper-mcp`.

---

## Step 2: Load the Lua Script in REAPER

ReaperMCP talks to REAPER through a Lua script that runs inside REAPER and polls for commands via file-based IPC.

1. Open **REAPER**
2. Go to **Actions → Show action list**
3. Click **Load ReaScript...**
4. Navigate to `reaper_scripts/reaper_mcp_server.lua` and select it
5. Click **Run**

> **You only need to do this once.** REAPER remembers loaded scripts. The script must be running for MCP to work — if REAPER restarts, re-run the script from Actions.

> **Keep REAPER open** — the connection only works while REAPER is running with the Lua script active.

## Step 3: Connect Your AI Client

Pick your client below. Each section shows the **complete config** — copy it and you're done.

### Claude Desktop

**Option A: Installed with pip** (simplest config)

If you installed via `pip install -e .` or the one-click installer, your config is just:

```json
{
  "mcpServers": {
    "reaper": {
      "command": "reaper-mcp"
    }
  }
}
```

**Option B: Running from source** (no pip install)

If you skipped `pip install` and want to run directly from the cloned repo:

Windows:
```json
{
  "mcpServers": {
    "reaper": {
      "command": "C:\\Users\\YourName\\AppData\\Local\\Programs\\Python\\Python311\\python.exe",
      "args": ["-m", "reaper_mcp.main"],
      "cwd": "C:\\Users\\YourName\\Projects\\Reaper-MCP"
    }
  }
}
```

macOS / Linux:
```json
{
  "mcpServers": {
    "reaper": {
      "command": "/usr/bin/python3",
      "args": ["-m", "reaper_mcp.main"],
      "cwd": "/Users/yourname/Projects/Reaper-MCP"
    }
  }
}
```

> **How to find your Python path:** Run `where python` (Windows) or `which python3` (macOS/Linux).
> On Apple Silicon with Homebrew, the path is usually `/opt/homebrew/bin/python3`.

**Already have other stuff in your config?** Just add the `"reaper"` key inside the existing `mcpServers`:

```json
{
  "mcpServers": {
    "reaper": {
      "command": "reaper-mcp"
    },
    "some-other-server": {
      "command": "some-other-command"
    }
  }
}
```

<details>
<summary>Config file locations</summary>

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json` (or `$XDG_CONFIG_HOME/Claude/` if set)

</details>

Save the config and **restart Claude Desktop**.

### Claude Code (CLI)

```bash
claude --mcp-server reaper=reaper-mcp
```

Or add to your project's `.mcp.json` for persistent config:

```json
{
  "mcpServers": {
    "reaper": {
      "command": "reaper-mcp",
      "type": "stdio"
    }
  }
}
```

### Cursor

1. Open **Settings** → **Tools & MCP** → **New MCP Server**
2. Set type to `command`, enter `reaper-mcp`
3. Done

Or create `.cursor/mcp.json` in your project root (or `~/.cursor/mcp.json` for global):

```json
{
  "mcpServers": {
    "reaper": {
      "command": "reaper-mcp"
    }
  }
}
```

### Other MCP Clients

ReaperMCP uses **stdio transport**. Point any MCP-compatible client at the `reaper-mcp` command.

### Reducing the tool surface for smaller models

ReaperMCP exposes 162 tools by default. Smaller or cheaper LLMs (Groq Llama 3 caps at 128, Claude Haiku and some local models lower still) will silently truncate. Set `REAPER_MCP_PROFILE` in your client's `env` block to register only a workflow-specific subset:

| Profile | Tools | For |
|---------|------:|-----|
| `full` *(default)* | ~162 | Claude, GPT-4, Gemini-class models |
| `composition` | ~118 | Writing / editing music (incl. vocal chops + helpers) |
| `mixing` | ~67 | Mixing, mastering, bus pipelines |
| `analysis` | ~47 | Inspect + measure only |
| `minimal` | ~40 | Smoke test / basic control |

```json
{
  "mcpServers": {
    "reaper": {
      "command": "reaper-mcp",
      "env": { "REAPER_MCP_PROFILE": "mixing" }
    }
  }
}
```

---

## Verify It Works

1. **Open REAPER** (with the Lua script running)
2. Open your AI client
3. Ask it:

```
"Get info about the current REAPER project"
```

If you see project info come back, you're all set.

---

## Next Step: Set Up Your Project

ReaperMCP needs VST instruments loaded on tracks before the AI can compose. See the **[Project Setup Guide](PROJECT_SETUP.md)** for recommended templates:

- **Orchestral / Film / TV** — strings, brass, woodwinds, percussion, choir
- **Pop / Rock** — drums, bass, guitars, keys, vocals
- **EDM / Electronic** — kick, snare, hi-hats, bass, synths, pads

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| "No response from REAPER" | Lua script not running | Actions → Show action list → find `reaper_mcp_server.lua` → Run |
| Script not in Actions list | Never loaded | Click **Load ReaScript...** first to register it |
| "Connection timeout" | REAPER busy or script crashed | Wait or re-run the Lua script |
| "command not found: reaper-mcp" | Not installed | Run `pip install -e .` from repo folder |
| Config not working | Wrong path or JSON syntax | Copy the complete example above, validate JSON at jsonlint.com |
| Claude Desktop doesn't see ReaperMCP | Config not loaded | Restart Claude Desktop after editing config |
| Works on Windows but not macOS | IPC dir mismatch | Check REAPER console: the Lua server prints "IPC dir: ..." on start. On macOS it should be `$TMPDIR/reaper_mcp` (e.g. `/var/folders/.../T/reaper_mcp`), NOT `/tmp/reaper_mcp`. If it shows `/tmp`, make sure you updated `reaper_mcp_server.lua` from this repo. |
| Works on Windows but not Linux | IPC path issue | Check `/tmp/reaper_mcp` exists and is writable. |
| "externally-managed-environment" error during install.sh | Modern Python + PEP 668 | Re-run `install.sh` — it auto-retries with `--user`. Or use `pipx install -e .`. |
| `bash: ./install.sh: /bin/bash^M: bad interpreter` | Git on Windows converted line endings to CRLF | Run `bash install.sh` (don't execute directly), or `sed -i 's/\r$//' install.sh`. Pulling the latest repo with the new `.gitattributes` fixes this. |
