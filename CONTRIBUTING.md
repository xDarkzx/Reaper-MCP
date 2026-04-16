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
- Describe what your change does and why.
- Update `CHANGELOG.md` under the current unreleased section.

## Reporting issues

Open an issue on GitHub with:

- What you expected to happen.
- What actually happened.
- Steps to reproduce.
- Your OS, Python version, and REAPER version.
- Relevant stderr output from the MCP server (the `[reaper-mcp]` banner lines).
