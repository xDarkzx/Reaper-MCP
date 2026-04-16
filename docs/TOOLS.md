# Tools Reference

Complete reference for every MCP tool exposed by ReaperMCP — **147 tools across 22 modules**. Grouped by domain; each tool links to its source module.

> All tools are async. Numeric inputs are range-validated before being sent to REAPER. Track/item indices are 0-based.

> **Too many tools for your model?** Some LLMs cap the tool surface (Groq Llama 3 = 128, Claude Haiku + some local models have lower ceilings). Set the `REAPER_MCP_PROFILE` environment variable to trim the surface to a workflow-specific subset. See [Tool profiles](#tool-profiles) below.

## Tool profiles

Set `REAPER_MCP_PROFILE=<name>` in your MCP client's server config to register only a subset of modules. Default is `full` (everything).

| Profile | Modules | Approx. tools | Use when |
|---------|--------:|--------------:|----------|
| `full` | 22 | 147 | Default. You're on Claude / GPT-4 / Gemini-class models. |
| `composition` | 13 | ~104 | Writing or editing music. Drops FX, mix, sidechain, analysis. |
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
| [FX](#fx) | `fx_tools.py` | 14 |
| [FX Inventory](#fx-inventory) | `inventory_tools.py` | 2 |
| [Mix & Master](#mix--master) | `mix_tools.py` | 3 |
| [Sidechain](#sidechain) | `sidechain_tools.py` | 1 |
| [Bus Pipelines](#bus-pipelines) | `pipeline_tools.py` | 4 |
| [Composition Utility](#composition-utility) | `compose_tools.py` | 3 |
| [Composition Editing](#composition-editing) | `compose_edit_tools.py` | 9 |
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
| `item_get_all(track_index=-1)` | List every media item (optionally filtered by track). |
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

## FX Inventory

Discover what plugins the user has installed, and pin per-category favourites. Source: `inventory_tools.py`.

| Tool | Description |
|------|-------------|
| `fx_list_installed(category="")` | Return every installed plugin plus the best-available EQ / compressor / reverb / limiter / de-esser / gate / saturator / multiband / stereo tool, racks detected (Waves StudioRack, Blue Cat PatchWork, Kilohearts Snap Heap, …), and any user overrides. |
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
| `wipe_all_midi(tracks="")` | **The only correct way to clear MIDI.** Deletes every MIDI item, clears markers/regions, resets composition state. Pass `tracks="[0,1,2]"` for a partial wipe. |
| `reset_composition()` | Full project reset — wipe MIDI, delete all tracks, return to a blank slate. |
| `configure_tracks(tracks)` | Batch-create or rename tracks with VSTi, colour, volume, pan. |
| `setup_routing(sends)` | Batch-create track sends from a JSON description. |
| `add_markers_batch(markers)` | Add many markers and regions in one call (section-by-section arrangement). |
| `rewrite_cc(...)` | Replace CC data on one or more tracks without touching notes. |
| `edit_section(tracks, start_time, end_time, mode)` | Replace MIDI inside a time range. Modes: `all`, `notes_only`, `ccs_only`. |
| `setup_fx_chain(tracks)` | Batch-apply FX chains to multiple tracks from a single description. |
| `setup_effect_bus(...)` | Create an effect bus (usually reverb) with sends from chosen source tracks. |

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
