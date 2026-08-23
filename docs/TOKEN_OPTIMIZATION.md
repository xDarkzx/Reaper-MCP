# Token/context usage

Every registered tool's name, description, and input schema gets sent to
the model on every turn where tools are available — this is how the
underlying Messages API works (stateless per call), not something
specific to ReaperMCP. The `REAPER_MCP_PROFILE` env var (see
`reaper_mcp/tool_registry.py`) exists partly for exactly this reason: it
filters which tool modules get registered, directly controlling how much
of this repeats on every turn.

## Real, measured numbers

Measured via `describe_profile(...)` / `reaper-mcp --profile-info <name> --json`:

| Profile | Tools | Schema Chars | Instruction Chars | Total Chars | Approx. Tokens (~÷4) |
|---|---|---|---|---|---|
| `full` (default) | 182 | 94,473 | 13,125 | 107,598 | ~26,899 |
| `composition` | 136 | 62,503 | 7,639 | 70,142 | ~17,535 |
| `production` | 130 | 54,679 | 10,071 | 64,750 | ~16,187 |
| `mixing` | 83 | 44,888 | 7,751 | 52,639 | ~13,159 |
| `analysis` | 57 | 17,999 | 3,899 | 21,898 | ~5,474 |
| `minimal` | 47 | 12,420 | 1,687 | 14,107 | ~3,526 |

### Exact Tool Allowlists & Introspection

In addition to coarse module profiles, ReaperMCP supports exact tool allowlists (`REAPER_MCP_INCLUDE_TOOLS`, `REAPER_MCP_EXCLUDE_TOOLS`), custom profile files (`REAPER_MCP_PROFILE_FILE`), and an introspection CLI:

```bash
reaper-mcp --profile-info mixing --json
```

This was measured while investigating why a Claude Desktop conversation
driving both ReaperMCP and a separate audio-generation MCP server was
burning through usage quota unusually fast. ReaperMCP's `full` profile
(~23,745 tokens/turn) was roughly 4-5x the size of the other server's
entire footprint after that server's own tool docstrings were trimmed —
by a wide margin the dominant per-turn cost between the two.

## Decision: `full` profile is staying, deliberately

`composition` was briefly set in a client config as an optimization, then
**reverted** and left on `full`. Confirmed directly with the user: they
use both composition-side tools (tracks/MIDI/tempo/arranging) *and*
mixing/FX-side tools (EQ/compression/sidechain/sends/mix-mastering
pipelines) regularly — no profile smaller than `full` is safe without
risking a tool they actively depend on becoming unavailable to the
calling model.

**Do not switch this project's default profile, or recommend a smaller
profile to this user, without re-confirming their actual tool usage
first.** The token savings shown above are real, but silently narrowing
the available tool surface based on what a single observed session
happened to use is exactly the mistake that was caught and reverted here
— usage in one conversation is not evidence of what's used across all of
them. If usage patterns are ever confirmed to have narrowed for real
(e.g. the user explicitly says they no longer touch mixing tools),
`composition` is the next profile to consider, not `minimal` or
`analysis` — those cut into composition-side tools too.
