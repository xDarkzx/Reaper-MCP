# Tools Reference

Complete reference for every MCP tool exposed by ReaperMCP — **163 tools across 25 modules**. Grouped by domain; each tool links to its source module.

> All tools are async. Numeric inputs are range-validated before being sent to REAPER. Track/item indices are 0-based.

> **Too many tools for your model?** Some LLMs cap the tool surface (Groq Llama 3 = 128, Claude Haiku + some local models have lower ceilings). Set the `REAPER_MCP_PROFILE` environment variable to trim the surface to a workflow-specific subset. See [Tool profiles](#tool-profiles) below.

## Tool profiles

Set `REAPER_MCP_PROFILE=<name>` in your MCP client's server config to register only a subset of modules. Default is `full` (everything).

| Profile | Modules | Approx. tools | Use when |
|---------|--------:|--------------:|----------|
| `full` | 25 | 163 | Default. You're on Claude / GPT-4 / Gemini-class models. |
| `composition` | 16 | ~119 | Writing or editing music (incl. patterns, loops, vocal chops). Drops FX, mix, sidechain, analysis. |
| `mixing` | 10 | ~67 | Mixing / mastering / bus pipelines. Drops MIDI / composition. |
| `analysis` | 5 | ~47 | Inspect and measure only. Read-mostly workflow. |
| `minimal` | 3 | ~40 | Smoke test / basic control surface. |

**How to set it — Claude Desktop / Cursor / any MCP client with env support:**

```json
{
  "mcpServers": {
    "reaper": {
      "command": "reaper-mcp",
      "env": {
        "REAPER_MCP_PROFILE": "mixing"
      }
    }
  }
}
```

**From a shell:**

```bash
REAPER_MCP_PROFILE=composition reaper-mcp
```

On startup the server writes a banner to stderr confirming the active profile and module count. An invalid profile name logs a warning and falls back to `full`.

---

## Quick index

| Domain | Module | Count |
|--------|--------|------:|
| [Transport](#transport) | `transport_tools.py` | 11 |
| [Tracks](#tracks) | `track_tools.py` | 18 |
| [Track Templates](#track-templates) | `template_tools.py` | 4 |
| [Project](#project) | `project_tools.py` | 11 |
| [Items](#items) | `item_tools.py` | 13 |
| [Takes](#takes) | `take_tools.py` | 4 |
| [MIDI](#midi) | `midi_tools.py` | 13 |
| [MIDI Quantize / Humanize](#midi-quantize--humanize) | `quantize_tools.py` | 3 |
| [Markers & Regions](#markers--regions) | `marker_tools.py` | 6 |
| [Tempo Map](#tempo-map) | `tempo_tools.py` | 4 |
| [Envelopes](#envelopes) | `envelope_tools.py` | 3 |
| [Selection](#selection) | `selection_tools.py` | 9 |
| [Sends & Routing](#sends--routing) | `send_tools.py` | 7 |
| [FX](#fx) | `fx_tools.py` | 15 |
| [FX Inventory](#fx-inventory) | `inventory_tools.py` | 2 |
| [Mix & Master](#mix--master) | `mix_tools.py` | 3 |
| [Sidechain](#sidechain) | `sidechain_tools.py` | 1 |
| [Bus Pipelines](#bus-pipelines) | `pipeline_tools.py` | 4 |
| [Composition Utility](#composition-utility) | `compose_tools.py` | 3 |
| [Composition Editing](#composition-editing) | `compose_edit_tools.py` | 9 |
| [Patterns](#patterns) | `patterns_tools.py` | 2 |
| [Loop Library](#loop-library) | `loops_tools.py` | 3 |
| [Vocal Chops](#vocal-chops) | `chops_tools.py` | 10 |
| [Audio Analysis](#audio-analysis) | `analysis_tools.py` | 4 |
| [Demo](#demo) | `demo_tools.py` | 1 |

---

## Transport

Playback, recording, tempo and time-signature control. Source: `reaper_mcp/tools/transport_tools.py`.

| Tool | Description |
|------|-------------|
| `transport_play()` | Start playback from the edit cursor. |
| `transport_stop()` | Stop playback. |
| `transport_pause()` | Pause playback (cursor keeps position). |
| `transport_record()` | Start recording on armed tracks. |
| `transport_get_state()` | Return playing / paused / recording / stopped flags plus play position. |
| `transport_set_position(seconds)` | Move edit cursor to a time in seconds. |
| `transport_set_bpm(bpm)` | Set project tempo. |
| `transport_set_time_signature(numerator, denominator)` | Set time signature (e.g., 4/4, 3/4, 7/8). |
| `transport_toggle_repeat()` | Toggle looped playback. |
| `transport_toggle_metronome()` | Toggle metronome click. |
| `transport_set_playrate(rate)` | Change playback rate (1.0 = normal). |

## Tracks

Create, delete, rename, route, colour, freeze, and inspect tracks. Source: `track_tools.py`.

| Tool | Description |
|------|-------------|
| `track_get_all()` | List every track with name, volume, pan, mute/solo/arm flags. |
| `track_get_info(track_index)` | Detailed info for one track. |
| `track_create(index=-1, name="")` | Insert a new track at an index (or append). |
| `track_delete(track_index)` | Delete a track. |
| `track_rename(track_index, name)` | Rename a track. |
| `track_set_volume(track_index, volume_db)` | Set fader level in dB. |
| `track_set_pan(track_index, pan)` | Set pan (-1.0 = full left, 1.0 = full right). |
| `track_set_mute(track_index, mute)` | Mute / unmute. |
| `track_set_solo(track_index, solo)` | Solo / unsolo. |
| `track_set_record_arm(track_index, arm)` | Arm / disarm for recording. |
| `track_set_color(track_index, r, g, b)` | Set track colour from RGB (0–255 each). |
| `track_select(track_index, selected=True, exclusive=False)` | Select (optionally exclusively) a track. |
| `track_set_input(track_index, input_index)` | Assign a REAPER input channel. |
| `track_get_mixer_state()` | Snapshot of every track's mixer state in one call. |
| `track_get_peak(track_index)` | Current peak meter reading in dB. |
| `track_freeze(track_index)` | Freeze a track to audio (bounces FX, reduces CPU). |
| `track_unfreeze(track_index)` | Unfreeze a frozen track. |
| `track_set_folder(track_index, folder_depth)` | Configure folder depth (`1` = start folder, `-1` = end, `0` = normal). |

## Track Templates

Save / load REAPER track templates so AI can reuse a configured instrument track. Source: `template_tools.py`.

| Tool | Description |
|------|-------------|
| `track_template_save(track_index, name)` | Save a track (with its FX chain) as a template. |
| `track_template_apply(name, track_index)` | Apply a saved template to a track. |
| `track_template_list()` | List every available template name. |
| `track_template_delete(name)` | Delete a saved template. |

## Project

Project lifecycle, save/load, rendering, undo. Source: `project_tools.py`.

| Tool | Description |
|------|-------------|
| `project_get_info()` | Project path, length, BPM, time signature, sample rate. |
| `project_new()` | Create a new empty project. |
| `project_open(path)` | Open a project file. |
| `project_save()` | Save the current project. |
| `project_save_as(path)` | Save the project to a new path. |
| `project_export_audio(path, format="wav")` | Render the project to audio. Supported formats: `wav`, `mp3`, `ogg`, `flac`, `aiff`. |
| `project_undo()` | Undo the last action. |
| `project_redo()` | Redo the last undone action. |
| `project_get_notes()` | Get the project's notes field (metadata). |
| `project_set_notes(notes)` | Replace the project's notes field. |
| `project_set_grid(grid_division)` | Set grid division (e.g., `0.25` = quarter note). |

## Items

Media item CRUD, split, fades, move, drop MIDI or audio files. Source: `item_tools.py`.

| Tool | Description |
|------|-------------|
| `item_get_all(track_index=-1, max_results=200)` | List every media item (optionally filtered by track). Capped at `max_results` (ceiling 2000) to avoid dumping a chop-heavy project's full item list into context; response includes `truncated`/`returned` when capped. |
| `item_get_info(item_index)` | Position, length, fade, volume, mute state of an item. |
| `item_select(item_index, selected=True, exclusive=False)` | Select one item. |
| `item_split(item_index, position)` | Split an item at a time in seconds. |
| `item_delete(item_index)` | Delete an item. |
| `item_move(item_index, new_position)` | Move an item to a new start time. |
| `item_set_length(item_index, length)` | Set item length in seconds. |
| `item_set_volume(item_index, volume_db)` | Per-item volume trim in dB. |
| `item_set_mute(item_index, mute)` | Mute / unmute an item. |
| `item_set_fade(item_index, fade_in=-1, fade_out=-1)` | Set fade-in / fade-out lengths (seconds; `-1` leaves unchanged). |
| `item_insert_media(track_index, path, position=0.0)` | Drop an audio/MIDI file onto a track. |
| `item_create_midi(track_index, position=0.0, length=4.0)` | Create an empty MIDI item. |
| `item_move_to_track(item_index, dest_track_index)` | Relocate an item to another track. |

## Takes

Takes let you layer multiple performances on a single item. Source: `take_tools.py`.

| Tool | Description |
|------|-------------|
| `item_take_list(item_index)` | List all takes in an item. |
| `item_take_set_active(item_index, take_index)` | Make a specific take the active one. |
| `item_take_add(item_index)` | Add a new empty take. |
| `item_take_delete_active(item_index)` | Delete the currently-active take. |

## MIDI

Note insertion (single + batch), CC events, sorting, metadata. Source: `midi_tools.py`.

| Tool | Description |
|------|-------------|
| `midi_insert_note(item_index, pitch, start_qn, end_qn, velocity=96, channel=0)` | Insert a single note. Prefer the batch variant for ≥ 2 notes. |
| `midi_insert_notes_batch(item_index, notes)` | Insert many notes in one call. `notes` is a JSON array of `{pitch, start, end, velocity, channel}`. |
| `midi_get_notes(item_index, max_results=500)` | Read every note in an item (position, pitch, velocity). |
| `midi_set_note(item_index, note_index, ...)` | Edit an existing note (position, length, pitch, velocity, mute). |
| `midi_delete_note(item_index, note_index)` | Delete a note. |
| `midi_select_notes(item_index, select_all=True)` | Select or deselect every note in an item. |
| `midi_delete_all_notes(item_index)` | Wipe every note in an item (CCs remain). |
| `midi_insert_cc(item_index, time_qn, cc_num, value, channel=0)` | Insert a CC / pitch-bend / aftertouch event. |
| `midi_delete_cc(item_index, cc_index)` | Delete a CC event. |
| `midi_get_note_names()` | Return a lookup table mapping pitch → note name (C4, D#3, …). |
| `midi_count_events(item_index)` | Count notes and CCs — cheap substitute for a full read. |
| `midi_sort(item_index)` | Sort MIDI events by start time (required after bulk inserts). |
| `midi_set_item_extents(item_index, start_qn, end_qn)` | Resize the MIDI item to span a quarter-note range. |

> **Why can't I read CCs?** `midi_get_ccs` was removed on purpose — reading CC1/CC11 across a full orchestral arrangement would blow the AI's context window. Use `midi_count_events` if you need an event count, or ask the user to describe what they want.

## MIDI Quantize / Humanize

Timing utilities. Source: `quantize_tools.py`.

| Tool | Description |
|------|-------------|
| `midi_quantize(item_index, grid_qn, strength=1.0, swing=0.0)` | Snap notes to a grid. `strength` blends 0 (none) → 1 (full). |
| `midi_humanize(item_index, time_jitter_ms=10.0, velocity_jitter=5)` | Add random timing and velocity variation. |
| `project_set_ripple_mode(mode)` | Set edit ripple mode (0=off, 1=per-track, 2=all-tracks). |

## Markers & Regions

Section markers and region rendering boundaries. Source: `marker_tools.py`.

| Tool | Description |
|------|-------------|
| `marker_get_all()` | Every marker and region in the project. |
| `marker_add(position, name="", color_r=0, color_g=0, color_b=0)` | Add a positional marker. |
| `marker_add_region(start, end, name="", color_r=0, color_g=0, color_b=0)` | Add a region (used for batch render-per-region). |
| `marker_delete(marker_index)` | Delete a marker or region by index. |
| `marker_edit(marker_index, position=-1, name=None)` | Rename or move a marker. |
| `marker_go_to(marker_number)` | Move the edit cursor to a marker. |

> For adding many markers at once, see `add_markers_batch` in [Composition Editing](#composition-editing).

## Tempo Map

Tempo and time-signature markers across the project timeline. Source: `tempo_tools.py`.

| Tool | Description |
|------|-------------|
| `tempo_list_markers()` | List every tempo/time-signature change. |
| `tempo_add_marker(time, bpm, num=-1, denom=-1, linear=False)` | Insert a tempo change (and optional time-sig change). |
| `tempo_delete_marker(index)` | Delete a tempo marker. |
| `tempo_clear_all()` | Remove every tempo marker (project reverts to constant BPM). |

## Envelopes

Read and write automation envelopes on tracks, items, or FX parameters. Source: `envelope_tools.py`.

| Tool | Description |
|------|-------------|
| `envelope_get_points(track_index, envelope_name, ...)` | Read automation points from an envelope. |
| `envelope_add_points(track_index, envelope_name, points, ...)` | Write points (time, value, shape) to an envelope. |
| `envelope_clear_range(track_index, envelope_name, start, end)` | Delete every point inside a time range. |

## Selection

Time selection, loop points, item/track selection. Source: `selection_tools.py`.

| Tool | Description |
|------|-------------|
| `selection_set_time(start, end)` | Set the time selection. |
| `selection_get_time()` | Return the current time selection `(start, end)`. |
| `selection_set_loop(start, end)` | Set the loop region. |
| `selection_select_all_items()` | Select every item in the project. |
| `selection_deselect_all_items()` | Deselect every item. |
| `selection_select_all_tracks()` | Select every track. |
| `selection_deselect_all_tracks()` | Deselect every track. |
| `selection_get_selected_tracks()` | List indices of currently-selected tracks. |
| `selection_get_selected_items()` | List indices of currently-selected items. |

## Sends & Routing

Inter-track sends — aux sends, sidechain feeds, parallel buses. Source: `send_tools.py`.

| Tool | Description |
|------|-------------|
| `send_create(source_track, dest_track)` | Create a post-fader send. Returns the new send index. |
| `send_remove(track_index, send_index)` | Delete a send. |
| `send_get_all(track_index)` | List every send on a track. |
| `send_set_volume(track_index, send_index, volume_db)` | Send level in dB. |
| `send_set_pan(track_index, send_index, pan)` | Send pan (-1 L → 1 R). |
| `send_set_mute(track_index, send_index, mute)` | Mute a send. |
| `send_get_routing_diagram()` | ASCII routing diagram for the entire project — great for "show me what's feeding into what". |

## FX

Add, remove, configure plugins; read/write parameters; manage presets. Source: `fx_tools.py`.

| Tool | Description |
|------|-------------|
| `fx_add(track_index, fx_name)` | Add a plugin to a track by name (fuzzy match). |
| `fx_remove(track_index, fx_index)` | Remove the plugin at an FX-chain slot. |
| `fx_get_chain(track_index)` | List every plugin in the track's FX chain. |
| `fx_get_params(track_index, fx_index)` | All parameters of a plugin (index, name, value, min/max). |
| `fx_set_param(track_index, fx_index, param_index, value)` | Set a parameter by index. |
| `fx_set_param_by_name(track_index, fx_index, param_name, value)` | Set a parameter by name (fuzzy match). |
| `fx_enable(track_index, fx_index)` | Enable a plugin. |
| `fx_disable(track_index, fx_index)` | Disable a plugin (bypass). |
| `fx_show_ui(track_index, fx_index)` | Open the plugin's UI window. |
| `fx_get_preset(track_index, fx_index)` | Current preset name. |
| `fx_set_preset(track_index, fx_index, preset_name)` | Load a preset by name. |
| `fx_navigate_preset(track_index, fx_index, direction)` | Step next/previous preset (`direction` = -1 or 1). |
| `fx_get_instrument(track_index)` | Detect which VSTi (if any) is on a track. |
| `fx_move(track_index, fx_index, new_index)` | Reorder plugins within a chain. |
| `fx_rename(track_index, fx_index, new_name)` | Rename an FX instance's display label (cosmetic — plugin unchanged). Used by the mix engine to tag its own FX with `[MIX] ` so cleanup can find them without touching user-added FX. Requires REAPER 6.37+. |

## FX Inventory

Discover what plugins the user has installed, and pin per-category favourites. Source: `inventory_tools.py`.

| Tool | Description |
|------|-------------|
| `fx_list_installed(category="", full_list=False)` | Return every installed plugin plus the best-available EQ / compressor / reverb / limiter / de-esser / gate / saturator / multiband / stereo tool, racks detected (Waves StudioRack, Blue Cat PatchWork, Kilohearts Snap Heap, …), and any user overrides. `all_installed` caps at 150 entries unless `full_list=True`. |
| `set_fx_preferences(preferences)` | Pin a category → plugin mapping. Stored at `%APPDATA%/reaper_mcp/fx_prefs.json` (or `~/.config/reaper_mcp/` on *nix). |

## Mix & Master

Full mix and master pipelines driven by a named style profile. Source: `mix_tools.py`.

| Tool | Description |
|------|-------------|
| `engine_mix(style="", clean=True)` | Per-track EQ + compression + reverb bus routing tuned for the style. Auto-detects FabFilter (Pro-Q 3 / Pro-C 2 / Pro-R) and falls back to REAPER stock. Orchestral profiles are also supported. |
| `engine_master(style, clean=True)` | Master-bus mastering chain: HP 25 Hz → bus glue comp → tonal shelf EQ → stereo width → brick-wall limiter, with style-appropriate LUFS and true-peak targets. |
| `engine_fix_mix(style="", include_master=True)` | Non-destructive mix repair — re-runs the pipeline on an existing session, preserving user tweaks where possible. |

**Supported styles (25):**

- **EDM (11):** `melodic_dubstep`, `big_room`, `future_bass`, `future_house`, `deep_house`, `tech_house`, `progressive_house`, `dubstep`, `trap`, `drum_and_bass`, `trance`
- **Rock (6):** `alt_rock`, `classic_rock`, `pop_rock`, `hard_rock`, `punk`, `post_rock`
- **Pop (4):** `modern_pop`, `dance_pop`, `indie_pop`, `rnb_pop`
- **Electronic (4):** `synthwave`, `lofi`, `ambient`, `hiphop`

## Sidechain

Kick → bass / pad / vocal pumping with pin-mapped sidechain inputs. Source: `sidechain_tools.py`.

| Tool | Description |
|------|-------------|
| `setup_sidechain(source_track, target_track, amount, ...)` | Auto-creates an aux send on channels 3/4, pin-maps the compressor's sidechain input, and tunes attack / release / ratio / threshold from a single `amount` dial (0 – 1). Works with REAPER's ReaComp or FabFilter Pro-C 2. |

## Bus Pipelines

Whole-bus recipes — parallel compression, drum bus, vocal chain, stem bouncing. Source: `pipeline_tools.py`.

| Tool | Description |
|------|-------------|
| `setup_parallel_compression(source_tracks, bus_name="BUS: Parallel Comp", ...)` | Route a group of tracks to a heavily-compressed parallel bus (New York compression). |
| `setup_drum_bus(source_tracks, bus_name="BUS: Drums", ...)` | Create a drum bus with glue compression and optional saturation. |
| `setup_vocal_chain(track_index, hp_freq=100.0, ...)` | Pro vocal chain on a track: HP → de-esser → compression (2 stages) → EQ → saturation. |
| `bounce_stems(track_indices, output_dir="", ...)` | Render each selected track individually to a WAV stem. |

## Composition Utility

Read the current project state and write small targeted MIDI edits. Source: `compose_tools.py`.

| Tool | Description |
|------|-------------|
| `get_track_instruments()` | Detect the VSTi (plus plausible patch name) on each track — drives the AI's choice of what to write where. |
| `analyze_score(...)` | Return note statistics for the current project (range, density, key guess). |
| `compose_arrangement(tracks, clear_existing=False, ...)` | Insert notes on ≤ 2 tracks using shorthand or JSON — capped at 30 notes. For bigger writes use `midi_insert_notes_batch` or split across calls. |

## Composition Editing

Heavier-duty editing — project-scale wipes, section replacements, batch setup. Source: `compose_edit_tools.py`.

| Tool | Description |
|------|-------------|
| `wipe_all_midi(tracks="")` | **The only correct way to clear MIDI.** Deletes MIDI items only (audio items are left untouched), clears markers/regions on a full wipe, resets composition state. Pass `tracks="[0,1,2]"` for a partial wipe. |
| `reset_composition()` | Full project reset — wipe MIDI, delete all tracks, return to a blank slate. |
| `configure_tracks(tracks)` | Batch-create or rename tracks with VSTi, colour, volume, pan. |
| `setup_routing(sends)` | Batch-create track sends from a JSON description. |
| `add_markers_batch(markers)` | Add many markers and regions in one call (section-by-section arrangement). |
| `rewrite_cc(...)` | Replace CC data on one or more tracks without touching notes. |
| `edit_section(tracks, start_time, end_time, mode)` | Replace MIDI inside a time range. Modes: `all`, `notes_only`, `ccs_only`. |
| `setup_fx_chain(tracks)` | Batch-apply FX chains to multiple tracks from a single description. |
| `setup_effect_bus(...)` | Create an effect bus (usually reverb) with sends from chosen source tracks. |

## Patterns

High-affordance shortcuts for common MIDI patterns — the AI reaches for these directly instead of parsing shorthand. Source: `patterns_tools.py`.

| Tool | Description |
|------|-------------|
| `create_drum_pattern(track_index, pattern, item_index=-1, start_qn=0.0, steps_per_bar=16, bar_count=1, velocity=100, channel=9)` | Multi-lane step sequencer. Each line of `pattern` is one drum lane. Characters: `k`=kick, `s`=snare, `h`=hat closed, `o`=hat open, `c`=crash, `r`=ride, `t`=tom, `l`=low tom, `i`=high tom, `p`=clap, `b`=rimshot, `.`=rest. Auto-creates a MIDI item if `item_index=-1`. |
| `create_chord_progression(track_index, chords, item_index=-1, start_qn=0.0, chord_duration_qn=4.0, velocity=96, channel=0, base_octave=4)` | Parse chord names (`"Cm7, Fm7, Bb7, Eb"`) into voiced MIDI. Supports `maj`, `m`, `dim`, `aug`, `sus2`, `sus4`, `6`, `7`, `maj7`, `m7`, `9`, `m9`, `maj9`, `11`, `13`, `add9`, `dim7`, `7sus4`. Separators: comma, pipe, dash-with-spaces, newline. |

**Drum pattern example** — classic 16-step rock beat:

```
k...k...k...k...
....s.......s...
h.h.h.h.h.h.h.h.
```

**Chord progression examples:**

```
"Cm7, Fm7, Bb7, Eb"           # comma-separated
"Am - F - C - G"              # dash-separated
"Dm | G | Em | A"             # pipe-separated
```

Both tools return a `hint` field suggesting the AI's next step (e.g., *"Call midi_humanize() for timing variation"*).

## Loop Library

Point the AI at a sample-pack folder and have it scan, pick, and load loops into REAPER. Designed for well-labelled packs (Prime Loops, Splice, Loopmasters, Native Instruments Expansions) where BPM / key / role are encoded in filenames like `Kick_140BPM_Am_01.wav` or `Deep Sub Bass 128 F#m Loop.wav`. Source: `loops_tools.py`.

| Tool | Description |
|------|-------------|
| `scan_audio_folder(path, recursive=True, max_files=500)` | Walk a folder for audio files (.wav, .mp3, .flac, .aif, .ogg, .m4a). Parses BPM / key / role (kick / bass / pad / lead / fx / vocal / perc / snare / hat / …) from each filename. Returns distribution summary + per-file parsed metadata + a `hint` suggesting the next tool call. |
| `detect_common_bpm(file_paths)` | Given a JSON array of paths, return the most common BPM across their filenames. Use after picking candidate loops to decide what to pass to `transport_set_bpm`. |
| `load_loops(loops, project_bpm=0)` | Batch-load audio loops into REAPER on auto-created tracks. Each entry in the JSON array: `{track_name, file_path, position_sec=0}`. If `project_bpm > 0`, sets project tempo first so loops align with the grid. Returns tracks created / reused plus per-entry errors. |

**Typical AI pipeline:**

```
scan_audio_folder("D:/Music Production/Chillstep Express")
  → 87 files, mostly 140 BPM Am, clusters by role

detect_common_bpm([selected_paths])
  → 140

load_loops([
    {"track_name":"Kick", "file_path":"...", "position_sec":0},
    {"track_name":"Bass", "file_path":"...", "position_sec":0},
    {"track_name":"Pad",  "file_path":"...", "position_sec":0},
    ...
], project_bpm=140)

engine_mix("future_bass")
engine_master("future_bass")
```

No librosa / soundfile required. Filename parsing alone handles the 80% case for professionally-labelled sample packs. Files without parseable metadata are still scanned; their fields are null and the AI can skip them.

## Vocal Chops

Primitives for slicing, pitching, time-stretching, reversing, and duplicating audio items — the building blocks of vocal chop production. Style-agnostic; works for vocals, drums, FX, anything. Source: `chops_tools.py`.

The intended workflow: **user manually loads an audio item on a track in REAPER** (vocal acapella, drum break, etc.); AI then uses `track_get_all` + `item_get_all` to find it and these tools to chop it.

| Tool | Description |
|------|-------------|
| `item_split_at_transients(item_index)` | Slice an item at every detected transient using REAPER's native action. Sensitivity is set in REAPER's project preferences (Transient detection sensitivity). Returns the new chops in playback order with `item_index`, `position`, `length`, `offset_in_original_sec`. |
| `item_split_at_positions(item_index, positions)` | Manual split at a JSON list of absolute project-time positions. Use for grid-based chopping (1/16 cuts) or hand-picked slice points. Positions outside the item's range are silently ignored. |
| `take_set_pitch(item_index, semitones, take_index=-1)` | Pitch-shift a take by N semitones. Float, range -60 to +60. The core of "tune a chop to a chord tone". Pitch quality depends on REAPER's pitch shift mode setting (Élastique Pro Soloist preserves vocal formants). |
| `take_set_playrate(item_index, rate, preserve_pitch=True)` | Time-stretch by changing playrate. With `preserve_pitch=True` (default), audio plays slower/faster without pitch change. With `False`, becomes vinyl-style speed change (faster = higher pitch). Range 0.05–16.0. |
| `take_set_reversed(item_index)` | Reverse an item's audio. Uses REAPER's "Reverse items as new take" action — the reversed take becomes active, original is preserved. Reverse-cymbal-into-downbeat fills, breath-in vocal FX, glitchy chop reversals. |
| `item_duplicate(item_index, count, spacing_sec=0)` | Copy an item N times (1-100) at fixed spacing. Each copy preserves pitch / playrate / FX. Default spacing = item length (back-to-back). For 1/16 stutters at 128 BPM: `spacing_sec = 60/128/4 = 0.117`. Returns new item indices. |

**Phase 2 — high-level helpers** (built on top of the primitives + chord theory):

| Tool | Description |
|------|-------------|
| `analyze_chop_set(item_indices)` | Inspect a list of chops, classify each by duration (`hit` / `staccato` / `syllable` / `sustain`), return summary stats. Helps the AI decide which chops fit which musical role without doing audio content analysis. |
| `arrange_chops_to_chord_tones(item_indices, chord_progression, beats_per_chord=4, bpm=0, layout="follow", source_root="C")` | Pitch-in-place helper. For each chop in playback order, calculate the chord tone it should hit and shift it via `take_set_pitch`. Layouts: `follow` / `ascending` / `porter` / `root`. NOT a rearranger — use `chop_pipeline` for the real chop sequencer. |
| `stack_chop_layers(item_indices, intervals_semitones="[7, 12]")` | For each chop, create overlay clones at parallel pitch intervals on the same track. The classic future-bass stack: original + 5th + octave. Best applied to a SUBSET of chops, not every one. |

**Phase 3 — end-to-end pipeline** (the magic button):

| Tool | Description |
|------|-------------|
| `chop_pipeline(vocal_item_index, chord_progression, bpm=0, bars=4, style="chillstep", target_track_name="Vocal Chops", mute_original=True, source_key="C", seed=0)` | **One-shot vocal chop arrangement.** Creates a NEW track, places REORDERED slices from the source vocal on a rhythmic grid per style, pitches each to a chord tone, adds Porter-style stutters + harmony stacks, applies 5ms fades, mutes the original. Styles: `chillstep` (sparse atmospheric 6/16), `future_bass` (dense melodic 11/16), `porter` (syncopated bursts 9/16), `trap` (percussive 7/16). The AI just calls it once — the tool encodes chop production craft internally. |

**Typical AI workflow** for vocal chops (with Phase 2 helpers):

```
User loads vocal acapella on a track named "Vocal".

[AI]  track_get_all() → finds Vocal at track 2
      item_get_all(track_index=2) → vocal item is index 5
      transport_get_state() → confirms 128 BPM, F#m project key

      item_split_at_transients(item_index=5)
        → 12 chops at indices 5-16, in playback order

      analyze_chop_set([5,6,7,8,...,16])
        → "3 staccato, 7 syllable, 2 sustain"

      arrange_chops_to_chord_tones(
        item_indices=[5,6,7,8,...,16],
        chord_progression="F#m, D, A, E",
        beats_per_chord=4,
        layout="follow"
      )
        → AI walks chops, assigns each to a chord-tone shift via take_set_pitch.
          Output: per-chop chord assignment + applied pitch.

      stack_chop_layers(
        item_indices=[10, 13],   # the standout chops
        intervals_semitones="[7, 12]"
      )
        → adds 5th + octave overlay layers on those two chops.

      Optional dramatic moment:
        item_duplicate(item_index=10, count=4, spacing_sec=0.117)  # 1/16 stutter
        take_set_reversed(item_index=11)                           # reverse FX

User hits play → harmonized vocal chops cascade through the chord progression.
```

The AI brings the **musical decisions** (which chord progression, where stutters land). These tools handle the **mechanical work** + the chord-theory math.

## Audio Analysis

Objective mix metrics from a rendered WAV. Pair with `project_export_audio` + `engine_master` for a measure → correct loop. Source: `analysis_tools.py`.

Requires optional dependencies — install with `pip install 'reaper-mcp[analysis]'` (adds `numpy`, `soundfile`, `pyloudnorm`). If deps are missing, these tools simply aren't registered and the server logs a one-line hint to stderr.

| Tool | Description |
|------|-------------|
| `analyze_loudness(wav_path, reference="streaming")` | Integrated LUFS, true peak, RMS, crest factor. Computes delta against a reference target (`streaming` / `spotify` / `apple_music` / `youtube` / `broadcast` / `cinema` / `club`) and returns a plain-English hint. |
| `analyze_clipping(wav_path, threshold_db=-0.1)` | Count of samples at/above a clipping threshold, per channel and total. Default -0.1 dBFS catches anything near 0 dBTP. |
| `analyze_frequency_spectrum(wav_path)` | Bass / low-mid / mid / high-mid / presence / brilliance energy split in dB, plus spectral centroid (brightness proxy) and a tonal-balance hint. |
| `analyze_stereo_field(wav_path)` | Phase correlation (-1..+1), mid / side RMS, side-to-mid ratio, mono-compatibility hint. |

**Typical workflow:**

```
engine_master("melodic_dubstep")               # apply a mastering chain
project_export_audio("C:/renders/mix.wav")     # render the mix
analyze_loudness("C:/renders/mix.wav")         # did we hit -14 LUFS?
analyze_clipping("C:/renders/mix.wav")         # any true-peak overs?
engine_fix_mix(...)                            # correct if off-target
```

## Demo

| Tool | Description |
|------|-------------|
| `demo_edm_project(clean_first=True, bpm=140.0)` | Build a complete demo EDM project end-to-end — tracks, MIDI, mix, master. Useful as a smoke test and a reference for what the pipeline can do. |

---

## Legend

- **Shorthand** — most composition tools accept either a JSON array or ReaperMCP's compact shorthand notation. See `reaper_mcp/instructions/00_core.md` for the full grammar.
- **Qn / QN** — quarter notes (REAPER's preferred MIDI time unit).
- **Style** — one of the 25 style profile names listed under [Mix & Master](#mix--master).

For an end-to-end walk-through, see **[PROJECT_SETUP.md](PROJECT_SETUP.md)**. For architecture details, see **[ARCHITECTURE.md](ARCHITECTURE.md)**.
