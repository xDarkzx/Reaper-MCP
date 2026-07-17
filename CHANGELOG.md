# Changelog

All notable changes to ReaperMCP will be documented in this file.

## [Unreleased]

### Added

- **`chop_pipeline` — end-to-end vocal-chop arrangement (Phase 3)**. One tool call produces a real chopped vocal on a NEW track — not sliced-in-place, not pitched-in-place. Creates a "Vocal Chops" track, reads the source WAV behind a vocal item, generates 1/16-note candidate slices, applies a style-specific rhythmic pattern (which slots get chops vs. gaps), pulls slices from a SHUFFLED source-offset order so the arrangement is truly reordered (not sequential playback), pitches each placement to a chord tone, optionally stutters and harmony-stacks, adds 5 ms fades on every chop edge to prevent clicks, and mutes the original vocal. Styles encode chop-production craft so the AI doesn't have to re-derive it per call: `chillstep` (sparse 6/16), `future_bass` (dense 11/16 + 40% harmony stacks), `porter` (syncopated 9/16 with stutter clusters), `trap` (percussive 7/16). Two new Lua handlers back it: `item_get_source_info` (resolves the source file path + offset behind an item) and `chops_create_virtual_slice` (creates an item on a target track that references a specific time range of a source WAV — no audio bouncing required).
- **Vocal-chop Phase 2 helpers** (3 more tools on top of Phase 1 primitives):
  - `analyze_chop_set(item_indices)` — calls `item_get_info` per chop, classifies duration as `hit` / `staccato` / `syllable` / `sustain` so the AI can pick chops appropriate to each musical role without doing audio content analysis.
  - `arrange_chops_to_chord_tones(item_indices, chord_progression, beats_per_chord, bpm, layout, source_root)` — high-level pitch arranger. Walks chops in playback order, computes which chord each falls into (based on time + `beats_per_chord` + project tempo), picks a chord tone per `layout` (`follow` / `ascending` / `porter` / `root`), and applies pitch shifts via `take_set_pitch`. The Porter Robinson signature pattern (root → 5th → octave → 5th) is built in.
  - `stack_chop_layers(item_indices, intervals_semitones)` — for each chop, creates overlay clones on the same track at parallel pitch intervals. Default `[7, 12]` = perfect 5th + octave (the future-bass harmonized stack). Capped at 50 source chops to avoid mixer overload.
  - New Lua handler `item_clone_to_position` to support `stack_chop_layers` overlay placement; existing `item_duplicate` enhanced to return new item indices in its response.
  - Tool surface: 159 → 162 across 25 modules.
- **Vocal chops primitives** (`chops_tools.py`, 6 tools) — building blocks for slicing, pitching, time-stretching, reversing, and duplicating audio items. Style-agnostic; the AI brings the artistic decisions, these tools do the mechanical work. Designed for the workflow where the user loads a vocal manually onto a REAPER track and the AI inspects it via `track_get_all` + `item_get_all`, then chops:
  - `item_split_at_transients(item_index)` — REAPER's native transient-split action wrapped to return the resulting chops in playback order with their indices and offsets.
  - `item_split_at_positions(item_index, positions)` — manual split at a JSON list of absolute project-time positions. For grid-based chopping or hand-picked slice points.
  - `take_set_pitch(item_index, semitones, take_index=-1)` — per-take pitch shift in semitones via `D_PITCH`. Float, range -60..60. The core of "tune a chop to a chord tone".
  - `take_set_playrate(item_index, rate, preserve_pitch=True)` — time-stretch via `D_PLAYRATE`. With `preserve_pitch=True` (default) audio plays slower/faster without pitch change.
  - `take_set_reversed(item_index)` — reverse via REAPER's "Reverse items as new take" action. Original take preserved.
  - `item_duplicate(item_index, count, spacing_sec=0)` — copy an item N times via `SetItemStateChunk` (preserves all take properties). Default spacing = item length for back-to-back placement.
  - Tool surface: 153 → 159 across 25 modules.
- **Loop-library pipeline** (`loops_tools.py`, 3 tools) — point the AI at a sample-pack folder (Prime Loops, Splice, Loopmasters, Native Instruments Expansions) and it builds a working REAPER session from the loops it finds:
  - `scan_audio_folder(path, recursive=True, max_files=500)` — walks a folder, parses BPM / key / role from each filename via regex (`Kick_140BPM_Am_01.wav` → `bpm=140, key="Am", role="kick"`). Returns distribution summary so the AI sees the dominant tempo / key cluster at a glance. Handles `.wav`, `.mp3`, `.flac`, `.aif`, `.aiff`, `.ogg`, `.m4a`.
  - `detect_common_bpm(file_paths)` — given a JSON array of paths, returns the most common BPM with per-value vote counts and a confidence score.
  - `load_loops(loops, project_bpm=0)` — batch-load loops onto auto-created tracks. Finds or creates a track by name for each entry, sets project BPM if provided, returns per-entry errors without aborting the batch.
  - Uses only stdlib + (optional) soundfile for duration; no librosa / heavy DSP required.
  - Typical pipeline: `scan_audio_folder` → Claude picks loops → `transport_set_bpm` → `load_loops` → `engine_mix(style)` → `engine_master(style)`. Tool surface: 150 → 153.
- **`fx_rename(track_index, fx_index, new_name)`** — new tool + Lua handler
  (`TrackFX_SetNamedConfigParm("renamed_name", …)`) for renaming an FX's
  display label. Used internally by the mix engine to tag its own FX with
  the `[MIX] ` prefix so cleanup can distinguish them from user-added FX.
  Requires REAPER 6.37+. Tool surface: 149 → 150.

### Fixed

- **`item_get_all` and `fx_list_installed` had no output cap.** A chop-heavy
  project can have hundreds of items; a power user's plugin folder can have
  500+ entries. `fx_list_installed` is documented as a call the AI should
  make before every mix pass, so its `all_installed` dump compounded on
  every mixing session. Both now cap by default (`item_get_all` via a new
  `max_results` param, 200 default/2000 ceiling, matching the existing
  `midi_get_notes` convention; `fx_list_installed`'s `all_installed` caps at
  150 with a `full_list=True` opt-out) instead of dumping unbounded lists
  into the calling model's context on every call.
- **Unused `mido` dependency removed** from `pyproject.toml` — nothing in
  the codebase imports it; all MIDI work goes through the REAPER-side Lua
  bridge, not a Python MIDI library.
- **`analysis_tools`'s missing-dependency fallback was invisible at the
  registry level.** The module already degrades gracefully when `numpy`/
  `soundfile`/`pyloudnorm` aren't installed (skips registering its 4 tools
  instead of crashing), but `register()` still returns normally, so
  `tool_registry.py` counted it as a normal success with no signal that 4
  tools quietly vanished. Added a `degraded` check that surfaces this in the
  startup banner.
- **Composition/mix tool modules were silently excluded from every published
  copy of the repo.** The `.gitignore` rule added in the 0.3.0 release
  (`compose_*.py` / `mix_*.py`, meant for scratchwork) was broad enough to
  also catch the real, shipped `compose_tools.py`, `compose_edit_tools.py`,
  `mix_tools.py`, and `compose_helpers.py` — 15 tools including
  `wipe_all_midi`, `compose_arrangement`, `get_track_instruments`,
  `analyze_score`, `edit_section`, `engine_mix`, `engine_master`. The files
  existed on disk in the working tree (so local testing never caught it) but
  had never once been committed, so every clone of the repo shipped with
  `00_core.md`'s CRITICAL-rule tools missing entirely — `tool not found` for
  clients, while the forbidden fallbacks (`item_delete`,
  `midi_delete_all_notes`) were the only things that actually worked.
  Narrowed the `.gitignore` rule and committed the four files. Tool surface
  unchanged (163 across 25 modules) — these tools already counted, they just
  weren't shipping.
- **`wipe_all_midi` deleted audio items.** The Lua handler deleted every
  media item on the targeted tracks with no `TakeIsMIDI` check, so calling it
  on a track holding recorded audio silently destroyed it. Now skips items
  whose active take isn't MIDI; audio items are left in place.
- **`tool_registry.py` couldn't detect a missing module under the default
  `full` profile.** The existing "profile references a module that isn't on
  disk" sanity check only ran for restricted profiles (`composition`/
  `mixing`/`analysis`/`minimal`) — `full` has `allowed=None` (register
  whatever `pkgutil` finds on disk), so it had nothing to compare against and
  would have stayed silent through the exact bug above. Added
  `_EXPECTED_MODULES`, an explicit list of every module that should exist,
  checked against the registered set for every profile including `full`. A
  future `.gitignore`-style regression now prints a loud startup warning
  instead of shipping quietly incomplete.
- **`_safe_path` system-directory blocklist was Windows-only.** `item_tools.py`
  and `project_tools.py` guarded against reading/writing REAPER paths under
  `C:\Windows` / `Program Files`, but only when `sys.platform == "win32"` —
  on macOS/Linux there was no equivalent check at all, so `/etc`, `/usr`,
  `/bin`, `/boot`, `/proc`, `/sys`, `/dev`, `/System`, `/Library` were
  unguarded. Added a matching `_BLOCKED_DIRS_NIX` list with a boundary-safe
  prefix check.
- **Mix cleanup no longer nukes user-added FX.** The mix engine now tags
  every FX it adds via `setup_fx_chain` / `setup_master_chain` with a
  `[MIX] ` prefix. Cleanup matches the prefix first; it only falls back to
  the old substring-name match if no tagged FX are found on a track
  (backward compat for projects from before this change or REAPER < 6.37).
  Users can now freely keep their own `ReaEQ` / `ReaComp` / `Pro-Q 3` /
  `Pro-C 2` instances on tracks they're also running the mix engine on.
- **Lua JSON encoder preserves full float precision.** The previous
  `"%.6f"` format truncated MIDI positions to microsecond granularity
  (roughly 48 samples at 48 kHz), which caused quiet drift on sub-sample
  batch inserts. Now `"%.17g"` — full IEEE-754 double round-trip.

### Fixed

Hardening pass following a full code audit. No API changes — all behaviour
fixes, validation improvements, and bug fixes.

**Mix engine (critical):**
- `mix_engine/plugins.py` — ReaVerbate dry gain was hardcoded to 1.0 on reverb
  return buses, meaning the dry signal passed through the bus alongside the
  wet tail, doubling the return level (~3 dB too loud). Now 0.0.
- `mix_engine/plugins.py` — Pro-R `Decay` parameter was being fed `room_size`,
  which collapsed the decay tail when room_size was small and duplicated Space
  otherwise. Removed the redundant Decay mapping; Pro-R's Space already
  encodes decay behaviour.
- `mix_engine/master.py` — FabFilter Pro-L 2 `Output Level` formula was
  `0.5 + true_peak_db / 60.0`, which for a target of -1 dBTP produced a
  ceiling at ~-31 dBTP (limiter barely engaged). Correct formula is
  `1.0 + true_peak_db / 60.0`, giving a ceiling at -1 dBTP as intended.
- `mix_engine/__init__.py` — cleanup now logs every FX it removes (at INFO
  level) plus a summary count, so users can audit what `clean=True` did.
  Added a `LIMITATION` docstring warning that substring matches on
  ReaEQ / ReaComp / Pro-Q 3 / Pro-C 2 will also remove user-added instances
  on tracks being mixed (scoped to `track_indices` only, other tracks safe).

**Core IPC:**
- `reaper_client.py` — JSON parse-failure retries now require the response
  file's mtime to CHANGE before counting another failure. Previously a
  partial mid-write response would hit max_parse_failures in 150 ms even
  when the real response was still on its way, rejecting legitimate
  responses under heavy write contention.
- `reaper_client.py` — `UnicodeDecodeError` is now caught and treated as a
  parse failure (same retry path). Previously it propagated as an
  unhandled exception if Lua wrote a byte that wasn't valid UTF-8.

**Lua bridge:**
- `reaper_mcp_server.lua` — `\uXXXX` JSON escapes are now decoded properly
  to UTF-8 (was being dropped to `?`). Track / plugin names with accented
  or CJK characters now round-trip correctly.
- `reaper_mcp_server.lua` — directory creation no longer uses `os.execute`
  with a shell-concatenated path. Uses REAPER's native
  `RecursiveCreateDirectory` API when available (safer against adversarial
  TMPDIR values), with a defensive-quoted shell fallback for very old REAPER.
- `reaper_mcp_server.lua` — added `Undo_BeginBlock` / `Undo_EndBlock` wrapping
  for every MIDI and item/track mutation that lacked it: `midi_insert_note`,
  `midi_insert_notes_batch`, `midi_set_note`, `midi_delete_note`,
  `midi_delete_all_notes`, `midi_insert_cc`, `midi_delete_cc`,
  `item_create_midi`, `track_create`. Undo history in REAPER now shows
  readable `MCP: …` labels for every change the AI made, so users can
  undo specific AI edits individually.

**Tool modules:**
- `tools/patterns_tools.py` — `start_qn` was being applied twice (once to the
  auto-created item's project position and again to every note inside the
  item), so patterns appeared at 2 × start_qn instead of start_qn. Now notes
  are placed relative to the item and the item always starts at project 0
  when auto-creating; users wanting a specific project position should
  pre-create the item with `item_create_midi`.
- `tools/patterns_tools.py` — chord regex now accepts lowercase roots
  (`"cm7"` parses the same as `"Cm7"`). Previously lowercase chord names
  silently returned None and were listed under `failed_chords`.
- `tools/analysis_tools.py` — `analyze_loudness` guards against silent audio
  (previously returned non-JSON `-inf` LUFS). `analyze_frequency_spectrum`
  guards against divide-by-zero when magnitudes sum to 0. `analyze_stereo_field`
  guards against divide-by-zero when either channel is constant / silent
  (was returning `NaN`, which breaks JSON serialisation).
- `tools/midi_tools.py` — `midi_insert_notes_batch` now validates the `notes`
  JSON client-side: parses it, checks shape is a list, enforces 50 000-note
  ceiling, validates every note has pitch (0-127), velocity (1-127), numeric
  start/end with end > start. Lua-side errors for malformed batches are now
  rare; when they happen, users get a precise Python-side message pointing
  to the bad note index and field.
- `tools/compose_edit_tools.py` — the "all" sentinel for `tracks=` is now
  case-insensitive and tolerates surrounding whitespace / quotes. Previously
  only `"all"`, `'all'`, and `"\"all\""` worked; `" ALL "` or `"All"` fell
  through to JSON parsing and raised an obscure error.

**Registry:**
- `tool_registry.py` — after registration, warns if a profile references a
  module that isn't importable (profile definition out of sync with disk).

### Added

- **High-affordance pattern tools** (`patterns_tools.py`, 2 tools) — dedicated MCP tools for the most common MIDI writing tasks, so the AI reaches for them directly without having to learn `compose_arrangement`'s shorthand grammar:
  - `create_drum_pattern(track_index, pattern, …)` — multi-lane step-sequencer notation (k/s/h/o/c/r/t/l/i/p/b for GM drums, `.` for rests, 16 steps per bar by default). Auto-creates the MIDI item, defaults to GM drum channel 9.
  - `create_chord_progression(track_index, chords, …)` — parses chord names like `"Cm7, Fm7, Bb7, Eb"` or `"Am - F - C - G"` into voiced MIDI. Supports major/minor/dim/aug/sus2/sus4/6/7/maj7/m7/9/m9/maj9/11/13/add9/dim7/7sus4.
- **Tool profiles** via `REAPER_MCP_PROFILE` env var — trim the 149-tool surface down to a workflow-specific subset so it fits under LLM tool-count limits (Groq Llama 3 = 128, smaller models lower). Profiles: `full` (default, ~149), `composition` (~106), `mixing` (~67), `analysis` (~47), `minimal` (~40). Invalid values log a warning and fall back to `full`. Startup banner writes the active profile and module count to stderr.
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
