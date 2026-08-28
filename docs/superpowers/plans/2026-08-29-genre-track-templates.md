# Genre Track Templates (Part 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `setup_genre_template(style)` — a new tool that scaffolds a blank,
genre-appropriate REAPER project: one track per instrument role, named and
colored per a genre-flavored palette, with reverb busses and sends wired up,
before any MIDI/audio exists.

**Architecture:** A pure data/lookup module (`track_palette.py`) maps each
catalog role to one of 9 buckets and a genre-flavored color; an orchestration
module (`template.py`) creates tracks and reuses the mix engine's existing
`_v2_create_reverb_buses`/`_v2_route_sends` helpers (zero duplicated mixing
logic); a thin tool wrapper exposes it as `setup_genre_template`.

**Tech Stack:** Python (`reaper_mcp` package), existing `mix_engine`
catalog/profile system, pytest.

**Spec:** `docs/superpowers/specs/2026-07-20-genre-track-templates-design.md`
(Part 2 only — Part 1, the batch-coloring bug fix, is already shipped;
verified `native_color_from_array` in `reaper_scripts/reaper_mcp_server.lua`
and the documented `configure_tracks` docstring already implement it).

## Global Constraints

- No EQ/comp/volume/pan applied at this stage — that stays `engine_mix`'s
  job, run later once real content exists (spec: "Part 2 — Orchestration").
- A role or family not found in the bucket/palette maps must degrade to a
  neutral gray `(130, 130, 130)`, never raise (spec: "A role not found in
  this map falls back to bucket 'other'... degrades gracefully").
- Reuse `_v2_create_reverb_buses`/`_v2_route_sends` from `mix_engine`
  exactly as-is — no renaming, no refactor (spec: "same busses, same
  colors... zero duplicated logic").
- **Deviation from the spec, found by checking the live catalog before
  writing this plan:** the catalog now has 38 distinct role keys, not 34 —
  `bass_808` and `drums` were added after the spec was written and aren't
  in its bucket table. Both are included in Task 1 below (`bass_808`→bass,
  `drums`→drums_percussion) rather than left to silently fall back to gray.

---

## File Structure

- **Create:** `reaper_mcp/mix_engine/track_palette.py` — `ROLE_TO_BUCKET`,
  `ROLE_DISPLAY_NAMES`, `FAMILY_PALETTES`, `resolve_track_color()`,
  `resolve_display_name()`. Pure data + pure lookup, no REAPER/IPC.
- **Create:** `tests/test_track_palette.py` — unit tests for the above,
  including a regression test that diffs the bucket map against the live
  catalog's actual role keys (the exact check that would have caught the
  `bass_808`/`drums` gap automatically).
- **Create:** `reaper_mcp/mix_engine/template.py` — `build_genre_template(client, style)`,
  the orchestration function.
- **Create:** `reaper_mcp/tools/genre_template_tools.py` — the
  `setup_genre_template` MCP tool, following the same `register(mcp)`
  pattern every other tools module in this package already uses.
- **Modify:** `reaper_mcp/tool_registry.py` — add `"genre_template_tools"`
  to `_EXPECTED_MODULES` (line 137) and to the `"composition"` profile's
  `include_modules` (line 87).
- **Modify:** `docs/ARCHITECTURE.md` — bump the tool-module count and add
  `setup_genre_template` to wherever the tool list documents composition
  tools.

---

### Task 1: `track_palette.py` — role buckets, display names, color resolution

**Files:**
- Create: `reaper_mcp/mix_engine/track_palette.py`
- Test: `tests/test_track_palette.py`

**Interfaces:**
- Consumes: `reaper_mcp.mix_engine.profiles_v2.STYLE_PROFILES` (dict, already
  populated by catalog imports — test-only, to diff role keys).
- Produces:
  - `ROLE_TO_BUCKET: dict[str, str]`
  - `FAMILY_PALETTES: dict[str, dict[str, tuple[int, int, int]]]`
  - `resolve_track_color(role_name: str, family: str) -> tuple[int, int, int]`
  - `resolve_display_name(role_name: str) -> str`
  These four names are used as-is by Task 2 (`template.py`) — do not rename.

- [ ] **Step 1: Write the failing regression test**

Create `tests/test_track_palette.py`:

```python
"""Tests for reaper_mcp/mix_engine/track_palette.py.

Pure data/lookup logic — no REAPER/IPC needed. STYLE_PROFILES import
triggers the real catalog registration side effects, same as production
code does, so the coverage test below checks against live data, not a
hand-copied snapshot that can silently drift (it already caught a real
gap once: bass_808 and drums were added to the catalog after the
original design doc's role-bucket table was written).
"""

from reaper_mcp.mix_engine.profiles_v2 import STYLE_PROFILES
from reaper_mcp.mix_engine.track_palette import (
    ROLE_TO_BUCKET, FAMILY_PALETTES, resolve_track_color, resolve_display_name,
)


class TestRoleToBucketCoversCatalog:
    def test_every_role_in_the_live_catalog_has_a_bucket(self):
        all_roles = set()
        for profile in STYLE_PROFILES.values():
            all_roles.update(profile.instrument_roles.keys())
        missing = all_roles - set(ROLE_TO_BUCKET.keys())
        assert missing == set(), f"Roles with no bucket mapping: {missing}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_track_palette.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reaper_mcp.mix_engine.track_palette'`

- [ ] **Step 3: Write the module**

Create `reaper_mcp/mix_engine/track_palette.py`:

```python
"""Role -> bucket mapping and genre-flavored track palette for
setup_genre_template (reaper_mcp/tools/genre_template_tools.py).

Pure data + pure lookup logic — no REAPER/IPC needed. See
docs/superpowers/specs/2026-07-20-genre-track-templates-design.md.
"""

ROLE_TO_BUCKET = {
    # drums_percussion
    "kick": "drums_percussion", "snare": "drums_percussion", "hats": "drums_percussion",
    "open_hat": "drums_percussion", "cymbals": "drums_percussion", "toms": "drums_percussion",
    "ride": "drums_percussion", "clap": "drums_percussion", "perc": "drums_percussion",
    "timpani_perc": "drums_percussion", "drums": "drums_percussion",
    # bass
    "bass": "bass", "bass_guitar": "bass", "sub_bass": "bass", "reese_bass": "bass",
    "growl_bass": "bass", "slap_bass": "bass", "upright_bass": "bass", "bass_808": "bass",
    # guitar
    "rhythm_guitar": "guitar", "lead_guitar": "guitar", "clean_guitar": "guitar",
    # keys
    "piano": "keys", "electric_piano": "keys",
    # synth_lead
    "lead_synth": "synth_lead", "pluck_synth": "synth_lead", "chord_stab": "synth_lead",
    # pad_atmosphere
    "pad": "pad_atmosphere",
    # vocal
    "vocal_lead": "vocal", "vocal_backup": "vocal", "vocal_chop": "vocal",
    # orchestral_section
    "strings_section": "orchestral_section", "brass_orchestral": "orchestral_section",
    "woodwinds": "orchestral_section", "choir": "orchestral_section",
    "horns_section": "orchestral_section",
    # fx
    "riser_fx": "fx", "impact_fx": "fx",
}

ROLE_DISPLAY_NAMES = {
    "kick": "Kick", "snare": "Snare", "hats": "Hi-Hats", "open_hat": "Open Hat",
    "cymbals": "Cymbals", "toms": "Toms", "ride": "Ride", "clap": "Clap",
    "perc": "Percussion", "timpani_perc": "Timpani/Perc", "drums": "Drums",
    "bass": "Bass", "bass_guitar": "Bass Guitar", "sub_bass": "Sub Bass",
    "reese_bass": "Reese Bass", "growl_bass": "Growl Bass", "slap_bass": "Slap Bass",
    "upright_bass": "Upright Bass", "bass_808": "808 Bass",
    "rhythm_guitar": "Rhythm Guitar", "lead_guitar": "Lead Guitar", "clean_guitar": "Clean Guitar",
    "piano": "Piano", "electric_piano": "Electric Piano",
    "lead_synth": "Lead Synth", "pluck_synth": "Pluck Synth", "chord_stab": "Chord Stab",
    "pad": "Pad",
    "vocal_lead": "Lead Vocal", "vocal_backup": "Backup Vocal", "vocal_chop": "Vocal Chop",
    "strings_section": "Strings", "brass_orchestral": "Brass", "woodwinds": "Woodwinds",
    "choir": "Choir", "horns_section": "Horns",
    "riser_fx": "Riser FX", "impact_fx": "Impact FX",
}

_FALLBACK_COLOR = (130, 130, 130)

FAMILY_PALETTES = {
    "rock": {
        "drums_percussion": (170, 80, 60), "bass": (120, 70, 55), "guitar": (200, 140, 60),
        "keys": (180, 160, 90), "synth_lead": (160, 100, 130), "pad_atmosphere": (110, 130, 110),
        "vocal": (200, 90, 70), "orchestral_section": (150, 110, 80), "fx": (140, 140, 140),
    },
    "pop": {
        "drums_percussion": (230, 90, 120), "bass": (90, 80, 200), "guitar": (240, 170, 60),
        "keys": (80, 190, 210), "synth_lead": (255, 140, 200), "pad_atmosphere": (150, 190, 240),
        "vocal": (255, 200, 60), "orchestral_section": (190, 150, 220), "fx": (200, 200, 200),
    },
    "edm": {
        "drums_percussion": (255, 60, 90), "bass": (140, 30, 220), "guitar": (255, 150, 30),
        "keys": (60, 220, 220), "synth_lead": (255, 210, 0), "pad_atmosphere": (80, 100, 240),
        "vocal": (255, 60, 200), "orchestral_section": (170, 90, 255), "fx": (0, 230, 180),
    },
    "electronic": {
        "drums_percussion": (200, 50, 70), "bass": (40, 160, 170), "guitar": (180, 120, 60),
        "keys": (90, 90, 200), "synth_lead": (0, 200, 160), "pad_atmosphere": (60, 70, 140),
        "vocal": (220, 100, 160), "orchestral_section": (130, 100, 180), "fx": (100, 200, 255),
    },
    "jazz": {
        "drums_percussion": (150, 60, 40), "bass": (40, 70, 110), "guitar": (170, 130, 50),
        "keys": (120, 40, 90), "synth_lead": (90, 130, 90), "pad_atmosphere": (70, 90, 100),
        "vocal": (180, 150, 70), "orchestral_section": (110, 70, 130), "fx": (90, 90, 90),
    },
    "orchestral": {
        "drums_percussion": (140, 90, 70), "bass": (60, 70, 90), "guitar": (150, 130, 100),
        "keys": (100, 80, 130), "synth_lead": (90, 120, 100), "pad_atmosphere": (120, 130, 150),
        "vocal": (170, 140, 110), "orchestral_section": (80, 100, 150), "fx": (110, 110, 110),
    },
    "funk_soul": {
        "drums_percussion": (200, 100, 40), "bass": (80, 50, 110), "guitar": (210, 180, 50),
        "keys": (60, 150, 130), "synth_lead": (220, 90, 150), "pad_atmosphere": (100, 90, 140),
        "vocal": (230, 150, 50), "orchestral_section": (200, 70, 60), "fx": (150, 150, 60),
    },
}


def resolve_track_color(role_name: str, family: str) -> tuple:
    """Look up the genre-flavored (r,g,b) color for a role, via its bucket.

    Unknown role or unknown family both degrade to a neutral gray rather
    than raising — a future catalog addition (new role, new family) must
    never hard-fail this tool.
    """
    bucket = ROLE_TO_BUCKET.get(role_name, "other")
    palette = FAMILY_PALETTES.get(family, {})
    return palette.get(bucket, _FALLBACK_COLOR)


def resolve_display_name(role_name: str) -> str:
    """Human-readable track name for a role, falling back to a title-cased
    version of the raw role key for any future catalog addition."""
    return ROLE_DISPLAY_NAMES.get(role_name, role_name.replace("_", " ").title())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_track_palette.py -v`
Expected: PASS

- [ ] **Step 5: Add the remaining unit tests**

Append to `tests/test_track_palette.py`:

```python
class TestResolveTrackColor:
    def test_known_role_and_family_returns_palette_color(self):
        assert resolve_track_color("kick", "rock") == (170, 80, 60)

    def test_unknown_role_falls_back_to_gray(self):
        assert resolve_track_color("some_future_role", "rock") == (130, 130, 130)

    def test_unknown_family_falls_back_to_gray(self):
        assert resolve_track_color("kick", "some_future_family") == (130, 130, 130)

    def test_every_family_has_all_nine_buckets(self):
        buckets = set(ROLE_TO_BUCKET.values())
        for family, palette in FAMILY_PALETTES.items():
            missing = buckets - set(palette.keys())
            assert missing == set(), f"{family} palette missing buckets: {missing}"


class TestResolveDisplayName:
    def test_known_role_uses_curated_name(self):
        assert resolve_display_name("vocal_lead") == "Lead Vocal"

    def test_unknown_role_falls_back_to_titlecased(self):
        assert resolve_display_name("some_future_role") == "Some Future Role"
```

- [ ] **Step 6: Run full file to verify everything passes**

Run: `pytest tests/test_track_palette.py -v`
Expected: PASS (7 tests: 1 coverage + 4 color + 2 display name)

- [ ] **Step 7: Commit**

```bash
git add reaper_mcp/mix_engine/track_palette.py tests/test_track_palette.py
git commit -m "feat: add role bucket/palette module for genre track templates"
```

---

### Task 2: `template.py` — orchestration

**Files:**
- Create: `reaper_mcp/mix_engine/template.py`
- Test: `tests/test_template.py` (the unknown-style error path only — the
  happy path needs a live REAPER track_create/track_rename/track_set_color
  round trip and is covered by Task 4's manual verification instead, same
  split this codebase already uses everywhere Lua/IPC is involved)

**Interfaces:**
- Consumes:
  - `reaper_mcp.mix_engine.track_palette.resolve_track_color`,
    `resolve_display_name` (Task 1).
  - `reaper_mcp.mix_engine._v2_create_reverb_buses(client, profile, plugin_profile) -> dict`
    (existing, returns `{bus_name: track_index}`).
  - `reaper_mcp.mix_engine._v2_route_sends(client, profile, role_map, bus_indices) -> int`
    (existing, `role_map` is `{track_index: role_name}`).
  - `reaper_mcp.mix_engine.detect.detect_plugins(client) -> PluginSuite` (existing).
  - `reaper_mcp.mix_engine.plugins.get_plugin_profile(suite)` (existing).
  - `reaper_mcp.mix_engine.profiles_v2.get_profile(name) -> StyleProfile | None`,
    `STYLE_PROFILES` (existing).
  - `client.execute("track_create", index=-1)` -> `{"success": true, "data": {"index": int, ...}}`
    (existing tool, confirmed response shape).
  - `client.execute("track_rename", track_index=int, name=str)` (existing tool).
  - `client.execute("track_set_color", track_index=int, r=int, g=int, b=int)` (existing tool).
- Produces: `build_genre_template(client, style: str) -> dict` — used as-is
  by Task 3 (`genre_template_tools.py`). Return shape:
  `{"success": True, "style": str, "family": str, "tracks_created": [...],
  "busses_created": [...], "sends_routed": int}`.

- [ ] **Step 1: Write the failing test for the unknown-style error path**

Create `tests/test_template.py`:

```python
"""Tests for reaper_mcp/mix_engine/template.py.

Only the unknown-style error path is unit-tested here — it's pure logic,
no REAPER needed. The happy path creates real tracks via client.execute
and is verified manually against live REAPER instead (same split this
codebase uses everywhere Lua/IPC is involved).
"""

import pytest

from reaper_mcp.mix_engine.template import build_genre_template
from reaper_mcp_shared.error_codes import ReaperMCPError


@pytest.mark.asyncio
async def test_unknown_style_raises_with_valid_style_list():
    with pytest.raises(ReaperMCPError) as exc_info:
        await build_genre_template(client=None, style="not_a_real_style")
    assert "not_a_real_style" in str(exc_info.value)
    assert "classic_rock" in str(exc_info.value)  # a real style name should be listed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_template.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reaper_mcp.mix_engine.template'`

- [ ] **Step 3: Write the module**

Create `reaper_mcp/mix_engine/template.py`:

```python
"""Orchestrates setup_genre_template: scaffold blank, named, colored,
genre-appropriate tracks + reverb busses + sends for a style, before any
MIDI/audio exists. No EQ/comp/volume/pan here — that's engine_mix's job,
run later once real content exists. See
docs/superpowers/specs/2026-07-20-genre-track-templates-design.md.
"""

from reaper_mcp.mix_engine import _v2_create_reverb_buses, _v2_route_sends
from reaper_mcp.mix_engine.detect import detect_plugins
from reaper_mcp.mix_engine.plugins import get_plugin_profile
from reaper_mcp.mix_engine.profiles_v2 import STYLE_PROFILES, get_profile
from reaper_mcp.mix_engine.track_palette import resolve_display_name, resolve_track_color
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


async def build_genre_template(client, style: str) -> dict:
    profile = get_profile(style)
    if profile is None:
        raise ReaperMCPError(
            ErrorCode.INVALID_PARAMETER,
            f"Unknown style '{style}'. Valid styles: {', '.join(sorted(STYLE_PROFILES))}",
        )

    suite = await detect_plugins(client)
    plugin_profile = get_plugin_profile(suite)

    tracks_created = []
    role_map = {}
    for role_name in profile.instrument_roles:
        result = await client.execute("track_create", index=-1)
        data = result.get("data", result)
        track_index = data["index"]

        display_name = resolve_display_name(role_name)
        await client.execute("track_rename", track_index=track_index, name=display_name)

        color = resolve_track_color(role_name, profile.family)
        await client.execute(
            "track_set_color", track_index=track_index,
            r=color[0], g=color[1], b=color[2],
        )

        role_map[track_index] = role_name
        tracks_created.append({
            "track_index": track_index, "role": role_name,
            "name": display_name, "color": list(color),
        })

    bus_indices = await _v2_create_reverb_buses(client, profile, plugin_profile)
    sends_routed = await _v2_route_sends(client, profile, role_map, bus_indices)

    return {
        "success": True,
        "style": style,
        "family": profile.family,
        "tracks_created": tracks_created,
        "busses_created": list(bus_indices.keys()),
        "sends_routed": sends_routed,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_template.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add reaper_mcp/mix_engine/template.py tests/test_template.py
git commit -m "feat: add build_genre_template orchestration"
```

---

### Task 3: `setup_genre_template` tool + registry wiring

**Files:**
- Create: `reaper_mcp/tools/genre_template_tools.py`
- Modify: `reaper_mcp/tool_registry.py:137-144` (add to `_EXPECTED_MODULES`)
- Modify: `reaper_mcp/tool_registry.py:85-95` (add to `"composition"` profile's `include_modules`)

**Interfaces:**
- Consumes: `reaper_mcp.mix_engine.template.build_genre_template(client, style)` (Task 2).
- Produces: MCP tool `setup_genre_template(style: str) -> dict`.

- [ ] **Step 1: Create the tool module**

Create `reaper_mcp/tools/genre_template_tools.py`:

```python
from mcp.server.fastmcp import FastMCP

from reaper_mcp.mix_engine.template import build_genre_template


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def setup_genre_template(style: str) -> dict:
        """Scaffold a genre-appropriate REAPER project: one track per
        instrument role, named and colored per a genre-flavored palette,
        with reverb busses and sends wired up — before any MIDI/audio
        exists.

        No EQ/comp/volume/pan is applied here. Run engine_mix(style) later,
        once there's real content on these tracks, for that. When the user
        names a specific plugin in conversation (e.g. "put Splice on the
        lead guitar"), call fx_add/setup_fx_chain directly — that's a
        separate, later step, not part of this tool.

        Args:
            style: Any style name from the mix-engine catalog, e.g.
                "classic_rock", "future_bass", "swing_jazz". An unknown
                name raises an error listing every valid style.
        """
        return await build_genre_template(client, style)
```

- [ ] **Step 2: Register the module**

Open `reaper_mcp/tool_registry.py`. Add `"genre_template_tools"` to
`_EXPECTED_MODULES` (around line 137-144):

```python
_EXPECTED_MODULES = frozenset({
    "analysis_tools", "chops_tools", "compose_edit_tools", "compose_tools",
    "demo_tools", "envelope_tools", "fx_tools", "genre_template_tools",
    "inventory_tools", "item_tools", "loops_tools", "marker_tools",
    "midi_tools", "mix_tools", "patterns_tools", "pipeline_tools",
    "project_tools", "quantize_tools", "script_tools", "selection_tools",
    "send_tools", "sidechain_tools", "take_tools", "template_tools",
    "tempo_tools", "track_tools", "transport_tools",
})
```

Add it to the `"composition"` profile's `include_modules` (around line
85-95):

```python
    "composition": ToolProfile(
        name="composition",
        include_modules={
            "transport_tools", "track_tools", "template_tools", "project_tools",
            "item_tools", "take_tools", "midi_tools", "quantize_tools",
            "marker_tools", "tempo_tools", "selection_tools",
            "compose_tools", "compose_edit_tools", "patterns_tools",
            "loops_tools", "chops_tools", "script_tools", "genre_template_tools",
        },
        instruction_packs=["core", "composition", "automation", "editing", "bbc_spitfire", "styles"],
    ),
```

- [ ] **Step 3: Run the full test suite**

Run: `pytest -v`
Expected: PASS, no regressions.

- [ ] **Step 4: Commit**

```bash
git add reaper_mcp/tools/genre_template_tools.py reaper_mcp/tool_registry.py
git commit -m "feat: add setup_genre_template tool"
```

---

### Task 4: Manual verification + docs

**Files:**
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 1: Verify MCP connection picks up the new tool**

Restart the MCP connection. Confirm `setup_genre_template` appears in the
available tool list (same pattern used throughout this session — a brand
new `@mcp.tool()` isn't visible until the server process reloads).

- [ ] **Step 2: Manually verify against live REAPER**

With REAPER open and connected, on an empty scratch project:
1. Call `setup_genre_template(style="classic_rock")`.
2. Confirm the response's `tracks_created` count matches
   `len(STYLE_PROFILES["classic_rock"].instrument_roles)`.
3. Visually confirm in REAPER: every created track has a non-empty name
   and a non-black color; reverb bus tracks (`MIX: Hall`, `MIX: Room`,
   `MIX: Plate` or whatever the style's `reverb_buses` specify) exist.
4. Call `engine_mix(style="classic_rock")` on the same project afterward
   and confirm every track gets matched (0 unmatched) — this is the real
   end-to-end proof that the track names line up with the profile's own
   aliases, per the spec's stated acceptance test.
5. Clean up the scratch tracks/project afterward.

- [ ] **Step 3: Update ARCHITECTURE.md**

Bump the tool-module count (`182 tools` if 181 was the count before this,
adjust to match whatever `pytest`/the running server reports) and add
`setup_genre_template` to wherever the composition tool list lives.

- [ ] **Step 4: Run the full test suite one final time**

Run: `pytest -v`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add docs/ARCHITECTURE.md
git commit -m "docs: add setup_genre_template to architecture docs"
```

---

## Plan Self-Review Notes

- **Spec coverage:** "New tool" / signature → Task 3. "Orchestration" steps
  1-6 → Task 2's `build_genre_template` line-by-line. "Role buckets" table
  → Task 1's `ROLE_TO_BUCKET` (plus the two roles the live catalog check
  found missing: `bass_808`, `drums`). "Palette" table → Task 1's
  `FAMILY_PALETTES`, values copied verbatim from the spec's table.
  "VST-on-mention" → documented as a workflow note in the tool's own
  docstring (Task 3), no code, matching the spec's own "no new tool" call.
  "Testing" section's unit-level items → Task 1 Step 1 (bucket coverage)
  and Task 2 Step 1 (unknown-style error); the `build_genre_template`
  live-run item and the manual acceptance test → Task 4 Step 2.
- **Type consistency checked:** `resolve_track_color`/`resolve_display_name`
  signatures match between Task 1's definition and Task 2's usage.
  `role_map` is `{track_index: role_name}` consistently in Task 2 and in
  `_v2_route_sends`'s existing signature. `build_genre_template(client, style)`
  matches between Task 2's definition and Task 3's usage.
- **No placeholders:** every step has complete, real code — no "add
  validation" or "similar to Task N" left unexpanded.
