# Changelog

All notable changes to ReaperMCP will be documented in this file.

## [Unreleased]

### Added

- **Audio analysis tools** (`analysis_tools.py`, 4 tools) — objective mix metrics from a rendered WAV, designed to pair with `project_export_audio` + `engine_master` for a `measure → correct` loop:
  - `analyze_loudness(wav_path, reference)` — integrated LUFS (pyloudnorm), true peak, RMS, crest factor, delta against streaming / broadcast / cinema / club targets.
  - `analyze_clipping(wav_path, threshold_db)` — per-channel and total sample-clip counts at a configurable threshold.
  - `analyze_frequency_spectrum(wav_path)` — 7-band energy split (sub / bass / low-mid / mid / high-mid / presence / brilliance), spectral centroid, tonal-balance hint.
  - `analyze_stereo_field(wav_path)` — phase correlation, mid / side RMS, side-to-mid ratio, mono-compatibility hint.
- **Optional `[analysis]` extras** — `numpy`, `soundfile`, `pyloudnorm`. Install with `pip install 'reaper-mcp[analysis]'`. Tools degrade silently and log a one-line hint to stderr if deps are missing, so the server stays up.

## [0.3.0] - 2026-04-17

### Added

- **25 style profiles** across EDM, Rock, Pop, and Electronic families — each with per-instrument EQ + compression curves, sidechain relationships, reverb bus configuration, and mastering targets (LUFS, true peak, stereo width, limiter character):
  - EDM (11): melodic_dubstep, big_room, future_bass, future_house, deep_house, tech_house, progressive_house, dubstep, trap, drum_and_bass, trance
  - Rock (6): alt_rock, classic_rock, pop_rock, hard_rock, punk, post_rock
  - Pop (4): modern_pop, dance_pop, indie_pop, rnb_pop
  - Electronic (4): synthwave, lofi, ambient, hiphop
- **`engine_master(style, clean=True)`** — master-bus mastering chain: HP 25 Hz → bus glue compression → tonal shelf EQ → stereo width → brick-wall limiter. Auto-detects FabFilter Pro-L 2 / Pro-C 2 / Pro-Q 3 or falls back to REAPER stock (ReaLimit / ReaComp / ReaEQ).
- **`engine_fix_mix(style="", include_master=True)`** — non-destructive mix repair. Re-runs the mix pipeline on an existing session, preserving user tweaks where possible.
- **`engine_mix(style)`** now dispatches to all 25 style profiles across EDM / Rock / Pop / Electronic in addition to the existing orchestral path.
- **`setup_sidechain(source, target, amount, ...)`** — professional sidechain compression. Creates an aux send on channels 3/4, pin-maps the compressor's sidechain inputs, and tunes attack / release / ratio / threshold from a single 0–1 amount dial. Auto-adds ReaComp or targets existing FabFilter Pro-C 2.
- **Bus pipelines** (`pipeline_tools.py`, 4 tools):
  - `setup_parallel_compression(source_tracks, bus_name, ...)` — New-York-style parallel compression bus.
  - `setup_drum_bus(source_tracks, bus_name, ...)` — drum bus with glue compression and optional saturation.
  - `setup_vocal_chain(track_index, hp_freq, ...)` — pro vocal chain: HP → de-esser → two-stage comp → EQ → saturation.
  - `bounce_stems(track_indices, output_dir, ...)` — render each selected track individually to a WAV stem.
- **FX inventory** (`inventory_tools.py`, 2 tools):
  - `fx_list_installed(category)` — discovers every installed plugin and picks the best-available EQ / compressor / reverb / limiter / de-esser / gate / saturator / multiband / stereo processor across FabFilter, Waves, iZotope, Valhalla, Softube, TDR, Slate, Melda, Soundtoys, Airwindows, and REAPER stock. Detects rack hosts (Waves StudioRack, Blue Cat PatchWork, Kilohearts Snap Heap).
  - `set_fx_preferences(preferences)` — pin category → plugin mapping. Stored at `%APPDATA%/reaper_mcp/fx_prefs.json` (or `~/.config/reaper_mcp/` on *nix).
- **Envelope automation** (`envelope_tools.py`, 3 tools): `envelope_get_points`, `envelope_add_points`, `envelope_clear_range` — read/write automation envelopes on tracks, items, and FX parameters.
- **Tempo map** (`tempo_tools.py`, 4 tools): `tempo_list_markers`, `tempo_add_marker`, `tempo_delete_marker`, `tempo_clear_all`.
- **Track templates** (`template_tools.py`, 4 tools): `track_template_save`, `track_template_apply`, `track_template_list`, `track_template_delete`.
- **Takes** (`take_tools.py`, 4 tools): `item_take_list`, `item_take_add`, `item_take_set_active`, `item_take_delete_active`.
- **Track freeze/unfreeze** (in `track_tools.py`): `track_freeze`, `track_unfreeze` — bounce FX to audio for CPU relief.
- **MIDI timing utilities** (`quantize_tools.py`, 3 tools): `midi_quantize`, `midi_humanize`, `project_set_ripple_mode`.
- **Composition editing expansion** (`compose_edit_tools.py`): `reset_composition`, `add_markers_batch`, `rewrite_cc`, `setup_fx_chain`, `setup_effect_bus` alongside the existing `wipe_all_midi`, `configure_tracks`, `setup_routing`, `edit_section`.
- **Demo** (`demo_tools.py`): `demo_edm_project(clean_first=True, bpm=140.0)` — build a full demo EDM project end-to-end as a smoke test and reference.
- **`send_get_routing_diagram`** — ASCII routing diagram for the whole project.
- **Lua handlers**: `setup_sidechain`, `setup_master_chain`, `setup_parallel_compression`, `setup_drum_bus`, `setup_vocal_chain`, `bounce_stems`, `fx_list_installed`, envelope and tempo-marker handlers — all support pin mappings and fuzzy FX param-name matching.
- **Heartbeat protocol** — the IPC client detects a stale REAPER (`server.lock` older than 60 s) and raises a typed `CONNECTION_LOST` error instead of hanging.
- **docs/TOOLS.md** — complete tool reference with every signature and one-line descriptions.
- **docs/ARCHITECTURE.md** — IPC protocol, mix-engine pipeline, and design-decision notes.

### Changed

- **AI-driven composition** — the AI writes every note, rhythm, CC curve, and keyswitch itself using the granular MIDI + FX tools. A single `00_core.md` instruction file provides the tool surface, shorthand notation, BBC Spitfire CC reference, and per-family mixing tips.
- `compose_arrangement` is now explicitly scoped to small edits (≤ 2 tracks, ≤ 30 notes); larger writes use `midi_insert_notes_batch` or split into chunks.
- README + CHANGELOG updated to reflect the current tool surface (143 tools across 21 modules).
- `pyproject.toml` bumped to `0.3.0`; description corrected from "TCP socket communication" to file-based IPC.

### Removed

- Internal composition generator and supporting modules (relocated outside the repo).
- `polish_track` and `add_smart_cc` tools — the AI does post-processing manually via `midi_set_note` / `midi_insert_cc`.
- `engine_compose`, `engine_next_layer`, `get_engine_options` — replaced by the AI-driven composition model.
- `midi_get_ccs` — reading CC curves across a full arrangement would blow the AI's context window. Use `midi_count_events` for a cheap count, or ask the user to describe their intent.

## [0.1.0] - 2026-03-16

### Added

- Initial release — 100+ MCP tools across 11 modules:
  - **Transport** (11): play, stop, pause, record, get state, set position, BPM, time signature, toggle repeat/metronome, set playrate
  - **Track** (15): get all/info, create, delete, rename, set volume/pan/mute/solo/record arm/color/input/folder, select, mixer state
  - **Project** (11): get info, new, open, save, save as, export audio, undo/redo, get/set notes, set grid
  - **FX** (14): add, remove, get chain, get/set params, params by name, enable/disable, show UI, preset get/set/navigate, get instrument, move
  - **Items** (13): get all/info, select, split, delete, move, set length/volume/mute/fade, insert media, create MIDI, move to track
  - **MIDI** (14): insert note (single/batch), get/set/delete notes, select notes, delete all, insert/get/delete CC, note names, count events, sort, set item extents
  - **Markers** (7): get all, add marker/region (single + batch), delete, edit, go to
  - **Selection** (9): get/set time selection, set loop, select/deselect all items/tracks, get selected
  - **Sends** (7): create, remove, get all, set volume/pan/mute, routing diagram
  - **Composition utility** (3): `get_track_instruments`, `analyze_score`, `compose_arrangement`
  - **Batch setup** (5): `edit_section`, `configure_tracks`, `setup_routing`, `setup_fx_chain`, `setup_effect_bus`
- Lua IPC bridge (`reaper_scripts/reaper_mcp_server.lua`) — file-based command/response via `%TEMP%\reaper_mcp` or `/tmp/reaper_mcp`
- Dynamic tool registration — drop a module into `reaper_mcp/tools/` with a `register(mcp)` function and it's auto-discovered
- Cross-platform support (Windows, macOS, Linux)
