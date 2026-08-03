# Contributing to ReaperMCP

Thanks for your interest in contributing! Every PR — tool, bug fix, doc, or test — is welcome.

## Development setup

```bash
git clone https://github.com/xDarkzx/Reaper-MCP.git
cd Reaper-MCP
pip install -e ".[dev]"
```

This installs `reaper-mcp` in editable mode along with `pytest` / `pytest-asyncio` for tests.

## Running tests

```bash
pytest tests/ -x -q
```

All tests must pass before submitting a PR.

## Running lint

```bash
ruff check .
```

CI runs this too — it only checks for real bugs (unused/undefined names, etc.) and
security-relevant patterns, not style or formatting, so it isn't fussy about how you
write code. Must pass clean before submitting a PR.

## Adding a new tool

1. Pick the right module in `reaper_mcp/tools/` — or create a new `*_tools.py` file. The tool registry auto-discovers any module that defines `register(mcp)`; helper files without that function are silently skipped.
2. Inside `register(mcp)`, define your tool with the `@mcp.tool()` decorator.
3. Validate numeric inputs (range-check) and string inputs (length-cap) before dispatching to REAPER.
4. Dispatch to the Lua bridge via `client.execute(command, **params)` — or `client.execute_long(...)` for bulk MIDI/FX writes that may take longer than 30 s.
5. Add a matching Lua handler in `reaper_scripts/reaper_mcp_server.lua` if you're introducing a new command.
6. Add tests in `tests/`.

Example:

```python
from reaper_mcp.reaper_client import ReaperClient

def register(mcp):
    client = ReaperClient()

    @mcp.tool()
    async def my_tool(param: float = 1.0) -> dict:
        """Short description of what this tool does.

        Args:
            param: What this parameter controls. Default: 1.0
        """
        if param < 0:
            raise ValueError("param must be >= 0")
        return await client.execute("MyCommand", param=param)
```

See `reaper_mcp/tools/transport_tools.py` for the simplest reference implementation.

## Adding a new mix style

1. Pick the right family file in `reaper_mcp/mix_engine/catalog/` (`edm.py`, `rock.py`, `pop.py`, `electronic.py`).
2. Add a profile dict keyed by the style name, listing the roles the style expects and their per-role EQ / compression / send / sidechain.
3. Update the role alias tables in `_shared.py` if your style introduces new role names the engine doesn't already recognise.

The mix engine walks live track names and matches them against the alias tables — no hard-coded track indices.

## External generation pipelines (TTS, voice synthesis, and similar)

If your contribution wraps an external generation service — text-to-speech,
voice synthesis, sample generation, anything that calls out to another API
or model and hands back a file — build it as a **separate MCP server**,
not as new tools inside reaper-mcp itself. This keeps reaper-mcp's
dependency surface and tool-schema size (which every connected client pays
for, on every turn) scoped to DAW control, and keeps generation pipelines
free to iterate on their own release cycle. Import the result into a
project with reaper-mcp's existing tools (`item_insert_media` and
friends) — no direct integration needed.

That raises a design choice worth thinking through before you build:
should the two servers stay fully independent, coordinated only by the AI
client calling tools from each in turn — or should one server also act as
an MCP *client* to the other, so a single tool call internally handles
generation and import together?

- **AI-orchestrated (recommended default).** Each server stays simple and
  independently useful. The AI sees the intermediate result (e.g. the
  generated audio) between steps, so it can adjust — regenerate with
  different lyrics, pick a different take, change where it lands — before
  committing to the import. The cost is an extra round-trip per pipeline
  run, which in practice is small.
- **Server-to-server (direct MCP client call).** Fewer round-trips, lower
  token cost for chained/repeated pipelines. The cost is real: the two
  servers become version-coupled, the AI loses visibility into (and the
  ability to steer) the intermediate step, and you're maintaining bespoke
  bridge code for every pairing. Only worth it once a pipeline is fixed
  and run often enough that the per-call overhead actually matters —
  don't reach for it by default.

Prefer the AI-orchestrated shape unless you have a concrete, measured
reason not to.

[SongForge-MCP](https://github.com/xDarkzx/SongForge-MCP) is a working
example of this pattern — a separate, local vocal/instrumental generation
server (no cloud service involved) whose output is meant to be imported
via reaper-mcp's own tools, AI-orchestrated rather than server-to-server.

## Running local ReaScripts

`script_tools.py` gives the AI a path to executing the user's own local
scripts — a materially bigger capability than everything else in this
tool surface, which only calls fixed, audited REAPER API functions
through our own handlers. If you extend this feature, keep the trust
boundary intact: discovery and execution stay hard-coded to REAPER's own
Scripts folder (`reaper.GetResourcePath() .. "/Scripts"`), never an
AI- or conversation-supplied path. Don't add a parameter that overrides
this.

## Code style

- Python 3.10+ (type hints on public surfaces).
- No comments or docstrings on obvious code — well-named identifiers are enough.
- Keep input validation explicit; error handling should mention the specific bad value.
- Lua files follow the same simplicity principle; each handler is explicit code.

## Security

- Validate every parameter before dispatch — range-check numeric inputs, length-cap strings, absolute-only for file paths.
- No dynamic code execution. The Lua bridge uses a static dispatch table; do not introduce `load` / `dofile` / `loadstring`.
- Never commit API keys or credentials. Secrets go in `.env` (already gitignored).

## Pull requests

- Keep PRs focused on a single change.
- Include tests for new tools.
- Make sure all existing tests still pass, and `ruff check .` is clean.
- Describe what your change does and why.
- Update `CHANGELOG.md` under the current unreleased section.

## Reporting issues

Open an issue on GitHub with:

- What you expected to happen.
- What actually happened.
- Steps to reproduce.
- Your OS, Python version, and REAPER version.
- Relevant stderr output from the MCP server (the `[reaper-mcp]` banner lines).
