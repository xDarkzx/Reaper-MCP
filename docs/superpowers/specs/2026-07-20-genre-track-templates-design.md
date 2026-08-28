# Genre Track Templates + Batch Coloring Fix — Design

Date: 2026-07-20
Status: Approved, pending implementation plan

## Background

Two related problems surfaced in the same session:

1. Claude Desktop tried to batch-color tracks via `configure_tracks` and it
   silently failed (tracks stayed black / didn't get the intended colors).
2. The user wants a way to scaffold a genre-appropriate REAPER project in one
   batch call — blank tracks, named and colored per instrument role, with
   reverb/other busses wired up the way a professional engineer would set up
   a session template — before any MIDI/audio exists. VST insertion on
   mention (e.g. "put Splice on the lead guitar") is explicitly a later,
   separate, conversational step, not part of the batch call.

The mix-engine catalog (`reaper_mcp/mix_engine/catalog/*.py`) already
contains 35 fully-specified style profiles (7 families: rock, pop, edm,
electronic, jazz, orchestral, funk_soul) with per-role EQ/comp/volume/pan,
reverb bus specs (room size, wet dB, color), and send routing. `engine_mix`
already knows how to apply all of that — but only to tracks that already
exist and happen to have names matching the profile's aliases. There is no
step that creates those tracks in the first place. This design adds that
step without duplicating the mixing logic.

## Part 1 — Batch coloring bug fix

### Root cause

`configure_tracks`'s Lua handler (`reaper_scripts/reaper_mcp_server.lua`,
`compose.configure_tracks`, ~line 2950) reads color as a positional array:

```lua
local r = clamp_color(entry.color[1] or 0)
local g = clamp_color(entry.color[2] or 0)
local b = clamp_color(entry.color[3] or 0)
```

Neither the Python tool (`reaper_mcp/tools/compose_edit_tools.py`,
`configure_tracks`) nor its docstring documents this format, and nothing on
either side validates it. If a caller passes `{"r":255,"g":0,"b":0}`, a hex
string, or normalized `0.0-1.0` floats (a reasonable guess, since most other
tools in this API — `fx_set_param`, pan — use normalized ranges), Lua's
`entry.color[1]` resolves to `nil`, `clamp_color(nil or 0)` → `0`, and the
track silently gets set to black instead of erroring. This is almost
certainly what happened to Claude Desktop's batch call — a silent
wrong-result, not a raised error.

### Fix

- **`reaper_mcp/tools/compose_edit_tools.py`** — `configure_tracks`:
  - Docstring: document `color` explicitly as `[r, g, b]`, each `0-255` int,
    e.g. `{"track_index":0, "color":[200,90,60]}`.
  - Validation: for each entry with a `color` key, require it's a list/tuple
    of exactly 3 items, each an `int` in `[0, 255]`. Raise
    `ReaperMCPError(ErrorCode.INVALID_PARAMETER, ...)` with a message naming
    the entry index and the expected format on any mismatch.
- **`reaper_scripts/reaper_mcp_server.lua`** — `compose.configure_tracks`:
  add an explicit guard: if `entry.color` is present but
  `entry.color[1]`/`[2]`/`[3]` aren't all numbers, return an error
  (`"Entry N: invalid color format, expected [r,g,b] with 0-255 ints"`)
  instead of defaulting to `0`. Defense in depth in case anything ever
  reaches this handler without going through the Python validation.

No change needed to `track_set_color` (single-track tool) — it already
takes `r`, `g`, `b` as separate int arguments, so there's no shape
ambiguity there. `setup_effect_bus`'s `bus_color` docstring already
documents the `"[r,g,b]"` format correctly; no change needed.

## Part 2 — Genre track templates

### New tool

`setup_genre_template(style: str) -> dict` in a new module
`reaper_mcp/tools/genre_template_tools.py` (auto-discovered by
`tool_registry.py` via `pkgutil.iter_modules`; add `genre_template_tools` to
`_EXPECTED_MODULES` and to the `composition` profile's module set in
`reaper_mcp/tool_registry.py`).

`style` accepts any of the 35 names already registered in
`STYLE_PROFILES` (same catalog `engine_mix`/`engine_master` use — e.g.
`classic_rock`, `alt_rock`, `hard_rock`, `punk`, `post_rock`, `pop_rock`,
`future_bass`, `swing_jazz`, `classical_chamber`, `classic_funk`, ...).
Unknown style name → `ReaperMCPError(ErrorCode.INVALID_PARAMETER, ...)`
listing valid names (same pattern `engine_mix` already uses for its style
catalog lookup failure).

### Orchestration

New module `reaper_mcp/mix_engine/template.py`, function
`build_genre_template(client, style: str) -> dict`:

1. Resolve `StyleProfile` via `get_profile(style)` (from `profiles_v2.py`,
   catalog already imported for side effects the way `engine_mix` does it).
2. Detect installed plugins the same way `engine_mix` does
   (`detect_plugins` / `get_plugin_profile`) — needed for the reverb bus FX
   chain entries in step 4.
3. For each `(role_name, role)` in `profile.instrument_roles.items()` (dict
   order is already curated per profile, e.g. kick → snare → hats → ... →
   vocal_backup):
   - `track_create` a new track.
   - `track_rename` to a display name from `ROLE_DISPLAY_NAMES` (new table
     in `reaper_mcp/mix_engine/track_palette.py`; falls back to
     `role_name.replace("_", " ").title()` if a role isn't in the table, so
     a future catalog addition never hard-fails this tool).
   - `track_set_color` using `resolve_track_color(role_name, profile.family)`
     (see palette below).
   - Record `{track_index, role, name, color}`.
4. Create reverb busses: import `_v2_create_reverb_buses` directly from
   `reaper_mcp.mix_engine` and call it as-is — no renaming, no refactor.
   This matches the codebase's existing precedent for reusing a
   leading-underscore helper across module boundaries within `mix_engine`
   (`master.py` already imports `_tag_mix_fx` from `mix_engine/__init__.py`;
   `fix_mix.py` already imports `_build_master_fx_chain` from `master.py`).
   Same busses, same colors, same FX chain selection (FabFilter Pro-R if
   present, else REAPER stock) `engine_mix` already produces — zero
   duplicated logic.
5. Route sends: same treatment for `_v2_route_sends`, imported and called
   directly with the `role_map` built from step 3 — a 1:1
   `{track_index: role_name}` mapping, since we just created those tracks
   ourselves (no alias-matching guesswork, unlike the `engine_mix` path,
   which has to reverse-match arbitrary live track names).
6. Return:
   ```json
   {
     "success": true,
     "style": "classic_rock",
     "family": "rock",
     "tracks_created": [{"track_index":0,"role":"kick","name":"Kick","color":[170,80,60]}, ...],
     "busses_created": ["hall", "room", "plate"],
     "sends_routed": 14
   }
   ```

No EQ/comp/volume/pan is applied at this stage. That remains
`engine_mix(style)`'s job, run later once there's real content — this keeps
the three phases (scaffold → compose → mix) distinct, matching the workflow
the user described.

### Role buckets

34 instrument-role keys currently exist across every catalog file. They
collapse into 9 buckets, covering all of them with no leftovers:

| Bucket | Roles |
|---|---|
| `drums_percussion` | kick, snare, hats, open_hat, cymbals, toms, ride, clap, perc, timpani_perc |
| `bass` | bass, bass_guitar, sub_bass, reese_bass, growl_bass, slap_bass, upright_bass |
| `guitar` | rhythm_guitar, lead_guitar, clean_guitar |
| `keys` | piano, electric_piano |
| `synth_lead` | lead_synth, pluck_synth, chord_stab |
| `pad_atmosphere` | pad |
| `vocal` | vocal_lead, vocal_backup, vocal_chop |
| `orchestral_section` | strings_section, brass_orchestral, woodwinds, choir, horns_section |
| `fx` | riser_fx, impact_fx |

A role not found in this map falls back to bucket `"other"`, which every
palette maps to a neutral gray `(130, 130, 130)` — so a future catalog
addition degrades gracefully instead of raising.

### Palette (genre-flavored, keyed by `profile.family`)

`reaper_mcp/mix_engine/track_palette.py` defines
`FAMILY_PALETTES: dict[str, dict[str, tuple[int,int,int]]]`, one 9-color
palette per family, each bucket getting a distinct, mood-appropriate shade:

Exact values, matching the precision of the existing `DEFAULT_REVERB_BUSES`
tuples (not left fuzzy):

| bucket | rock | pop | edm | electronic | jazz | orchestral | funk_soul |
|---|---|---|---|---|---|---|---|
| drums_percussion | (170,80,60) | (230,90,120) | (255,60,90) | (200,50,70) | (150,60,40) | (140,90,70) | (200,100,40) |
| bass | (120,70,55) | (90,80,200) | (140,30,220) | (40,160,170) | (40,70,110) | (60,70,90) | (80,50,110) |
| guitar | (200,140,60) | (240,170,60) | (255,150,30) | (180,120,60) | (170,130,50) | (150,130,100) | (210,180,50) |
| keys | (180,160,90) | (80,190,210) | (60,220,220) | (90,90,200) | (120,40,90) | (100,80,130) | (60,150,130) |
| synth_lead | (160,100,130) | (255,140,200) | (255,210,0) | (0,200,160) | (90,130,90) | (90,120,100) | (220,90,150) |
| pad_atmosphere | (110,130,110) | (150,190,240) | (80,100,240) | (60,70,140) | (70,90,100) | (120,130,150) | (100,90,140) |
| vocal | (200,90,70) | (255,200,60) | (255,60,200) | (220,100,160) | (180,150,70) | (170,140,110) | (230,150,50) |
| orchestral_section | (150,110,80) | (190,150,220) | (170,90,255) | (130,100,180) | (110,70,130) | (80,100,150) | (200,70,60) |
| fx | (140,140,140) | (200,200,200) | (0,230,180) | (100,200,255) | (90,90,90) | (110,110,110) | (150,150,60) |
| other (fallback, all families) | (130,130,130) |

These live in `FAMILY_PALETTES` as a literal dict of tuples, styled the
same way `DEFAULT_REVERB_BUSES` is written today — no abstraction beyond
what the existing catalog already uses for the same kind of data.

### VST-on-mention

No new tool. Confirmed with the user: when they name a plugin in
conversation (e.g. "put Splice on the lead guitar"), the AI calls the
existing `fx_add`/`setup_fx_chain` tools directly against the relevant
track index(es). This is a workflow convention, not a code change.

## Testing

- Unit-level: `ROLE_TO_BUCKET` covers every key currently in every
  `instrument_roles` dict across `reaper_mcp/mix_engine/catalog/*.py` (a
  test can assert this by importing the catalog and diffing role-key sets
  against the bucket map, so a future new role fails CI instead of silently
  falling back to gray).
- `configure_tracks` color validation: malformed shapes (dict, string,
  wrong length, out-of-range values, floats) are rejected with a clear
  error; a valid `[r,g,b]` list still works.
- `build_genre_template`: run for one style per family (7 runs) against a
  blank project, assert track count matches `len(profile.instrument_roles)`,
  every track has a non-empty name and a non-black color, bus count matches
  `len(profile.reverb_buses or DEFAULT_REVERB_BUSES)`, and sends count > 0
  for any profile where at least one role has a non-empty `sends` list.
- Manual: `setup_genre_template("classic_rock")` against a live REAPER
  instance, visually confirm track names/colors, then run
  `engine_mix("classic_rock")` afterward and confirm it matches every track
  (0 unmatched) since names now line up with the profile's own aliases.
