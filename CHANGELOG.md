# Changelog

All notable changes to ReaperMCP will be documented in this file.

## [0.5.0] - 2026-07-20

### Added

- **Automatic pre-action backup for destructive operations.** `wipe_all_midi`,
  `track_delete`, `item_delete`, and `engine_mix`/`engine_master` with
  `clean=True` (which removes existing FX before applying new ones) now
  save a timestamped snapshot copy of the project — once per project per
  session — before the destructive action runs, via a new shared
  `reaper_mcp/safety.py` helper. This is on top of, not a replacement for,
  REAPER's own undo history (already wrapped around every MCP action) — a
  durable on-disk copy survives a crash or an undo-depth limit that
  in-memory undo doesn't. A failed backup attempt logs a warning and lets
  the requested action proceed rather than blocking it.
- `project_backup(path)` — new tool: save a snapshot copy without changing
  the project's active file (unlike `project_save_as`, the next
  `project_save` still targets the original file). Powers the auto-backup
  above; also directly usable.
- `project_get_info` now returns `file_path` — the actual `.rpp` project
  file path (empty if never saved). The pre-existing `path` field is the
  recording/media directory, not the project file, and was easy to
  mistake for one.
- `00_core.md`: new guidance to describe destructive/hard-to-reverse
  actions on an existing project and wait for confirmation before running
  them, unless the user already gave clear specific instruction to do
  exactly that. Additive work (new tracks, MIDI on empty tracks, adding
  FX) proceeds directly as before.
- **REAPER auto-start on launch.** `install.sh`/`install.bat` now drop a
  `__startup.lua` into REAPER's `Scripts` resource folder — REAPER runs any
  script with that exact name automatically on every launch, natively, no
  Action-list registration needed. Removes the "load the Lua script every
  time REAPER opens" manual step for anyone who used the installer. If a
  `__startup.lua` already exists for something else, the installer appends
  to it (backed up as `__startup.lua.bak`) instead of overwriting it. Falls
  back to the old manual-load instructions if REAPER's resource folder
  doesn't exist yet (i.e. REAPER has never been run) — re-running the
  installer after REAPER's first launch picks it up.
- `engine_mix`'s v2 pipeline now returns `unmatched_tracks` — tracks whose
  name didn't match any role alias got no volume/EQ/comp, and any sidechain
  depending on them (e.g. kick→bass) silently never fired, with nothing in
  the response indicating why. A track named "Drums" (very normal for a
  single combined drum-machine track) never matches the "kick" alias list
  (`kick`/`bd`/`bass drum`/`kik`), so a trap mix could report full success
  with 0 sidechains applied and no clue what happened.
- `tests/test_patterns_tools.py` and `tests/test_safety.py` — 16 new tests
  covering the item-placement/pattern-tiling fixes and the auto-backup
  decision logic below. Full suite: 91 passing (was 75).

### Fixed

- **`project_save_as` never actually saved to the given path.** Its Lua
  handler called `reaper.Main_SaveProject(0, path)` — that function's
  second argument is a boolean ("force the Save-As dialog"), not a
  filename. Passing a string there is truthy in Lua, so every call just
  popped REAPER's interactive Save-As dialog and silently ignored the
  path entirely, which would hang any non-interactive caller waiting on a
  result. Switched to `Main_SaveProjectEx(0, path, 8)`, the actual
  non-interactive save-to-path API (option bit 8 = make this the active
  project file going forward, matching normal "Save As" semantics).
- **`create_drum_pattern`/`create_chord_progression`: auto-created items
  always landed at project position 0, ignoring `start_qn`.** Since
  `midi_insert_notes_batch` writes notes at absolute project time (not
  item-relative), a second call for a later section (e.g. a verse at bar 5
  after an intro at bar 1) created an item that overlapped the first one at
  position 0 instead of sitting after it — reproduced live: two 4-bar
  sections both landed with their item boundary at t=0. Item position now
  equals `start_qn` converted to seconds.
- **A drum-pattern lane shorter than `steps_per_bar * bar_count` silently
  only filled the first bar, leaving the rest empty — no warning.** Easy to
  trigger by assuming a 1-bar line auto-repeats across `bar_count` bars (a
  reasonable assumption the tool didn't honor). Now a line exactly
  `steps_per_bar` long auto-tiles across all bars; any other mismatched
  length raises an error instead of quietly truncating.
- The first fix above initially added a small trailing pad to auto-created
  item lengths as a safety margin; that pad itself caused a smaller overlap
  between two sections placed back-to-back with no gap (confirmed
  proportional: a 0.5s pad overlapped by 0.5s, a 0.05s pad by 0.05s).
  Removed entirely — each drum note already ends before the pattern's
  nominal end (see the `gate` shortening), and a chord's last note ends
  exactly at the same point the item does, so no pad was ever needed.
- `compose_arrangement` had a `bpm` parameter, documented as "Project BPM
  (default 120)", that was never referenced anywhere in the function body —
  a dead, misleading parameter. Shorthand note/CC times are raw seconds,
  entirely tempo-independent (unlike `create_drum_pattern`/
  `create_chord_progression`, which take quarter-notes and convert using
  the live project BPM). Removed the parameter; docstring now states the
  seconds-vs-quarter-notes split explicitly so the two conventions aren't
  mixed up.

## [0.4.0] - 2026-07-20

### Added

- **10 new mix-engine styles across 3 new genre families — Jazz, Orchestral,
  Funk/Soul (25 → 35 styles).**
  - **Jazz** (`swing_jazz`, `jazz_fusion`, `latin_jazz`): near-zero bus
    compression, wide dynamic range (-13 to -16 LUFS), no sidechain —
    dynamics are the performance, not something to flatten. New shared
    presets: `upright_bass`, `piano_jazz`, `ride_cymbal`, `vocal_jazz`,
    `comp_jazz_gentle`.
  - **Orchestral** (`classical_chamber`, `cinematic_trailer`,
    `ambient_orchestral`): pairs with the existing BBC Spitfire CC guidance
    in `00_core.md`. Minimal-to-zero bus compression, -16 to -20 LUFS
    targets (closer to a classical/broadcast master than streaming
    loudness — intentional). These are **consolidated-section** profiles
    (one "strings"/"brass"/"woodwinds"/"choir" track each) — for a full
    per-instrument multi-mic template (separate Violin 1/2, Viola, Cello,
    individual winds/brass), the pre-existing legacy orchestral path in
    `mix_engine/profiles.py` is still the finer-grained option and is what
    any style name outside the v2 catalog routes to (empty string
    included) — this was already true before this change and still is.
    New shared presets: `strings_section`, `brass_orchestral`, `woodwinds`,
    `choir`, `timpani_perc`, `comp_orchestral_glue`.
  - **Funk/Soul** (`classic_funk`, `motown_soul`, `neo_soul`,
    `disco_funk`): fast transient-catching compression instead of
    loudness-flattening compression. No kick↔bass sidechain in any of
    them — funk bass and kick play in rhythmic unison, so ducking one
    under the other fights the pocket instead of serving it. `neo_soul`
    uses a genuinely-pro technique instead — a subtle vocal→keys/horns
    duck (amount 0.2-0.25, slow release) so the vocal breathes room without
    riding a fader through every phrase; `disco_funk` uses a light
    kick→strings duck, since disco sits closer to dance music than the
    other three. New shared presets: `slap_bass`, `electric_piano`,
    `horns_section`, `vocal_soul`, `comp_funk_punch`, `comp_soul_vocal`,
    `comp_horns`.
  - `engine_mix`/`engine_master`'s docstrings and `00_core.md`'s style
    cheat sheet updated with per-family mixing tips for all three.
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
- **High-affordance pattern tools** (`patterns_tools.py`, 2 tools) — dedicated MCP tools for the most common MIDI writing tasks, so the AI reaches for them directly without having to learn `compose_arrangement`'s shorthand grammar:
  - `create_drum_pattern(track_index, pattern, …)` — multi-lane step-sequencer notation (k/s/h/o/c/r/t/l/i/p/b for GM drums, `.` for rests, 16 steps per bar by default). Auto-creates the MIDI item, defaults to GM drum channel 9.
  - `create_chord_progression(track_index, chords, …)` — parses chord names like `"Cm7, Fm7, Bb7, Eb"` or `"Am - F - C - G"` into voiced MIDI. Supports major/minor/dim/aug/sus2/sus4/6/7/maj7/m7/9/m9/maj9/11/13/add9/dim7/7sus4.
- **Tool profiles** via `REAPER_MCP_PROFILE` env var — trim the tool surface down to a workflow-specific subset so it fits under LLM tool-count limits (Groq Llama 3 = 128, smaller models lower). Profiles: `full` (default), `composition`, `mixing`, `analysis`, `minimal`. Invalid values log a warning and fall back to `full`. Startup banner writes the active profile and module count to stderr.
- **Audio analysis tools** (`analysis_tools.py`, 4 tools) — objective mix metrics from a rendered WAV, designed to pair with `project_export_audio` + `engine_master` for a `measure → correct` loop:
  - `analyze_loudness(wav_path, reference)` — integrated LUFS (pyloudnorm), true peak, RMS, crest factor, delta against streaming / broadcast / cinema / club targets.
  - `analyze_clipping(wav_path, threshold_db)` — per-channel and total sample-clip counts at a configurable threshold.
  - `analyze_frequency_spectrum(wav_path)` — 7-band energy split (sub / bass / low-mid / mid / high-mid / presence / brilliance), spectral centroid, tonal-balance hint.
  - `analyze_stereo_field(wav_path)` — phase correlation, mid / side RMS, side-to-mid ratio, mono-compatibility hint.
- **Optional `[analysis]` extras** — `numpy`, `soundfile`, `pyloudnorm`. Install with `pip install 'reaper-mcp[analysis]'`. Tools degrade silently and log a one-line hint to stderr if deps are missing, so the server stays up.

### Fixed

- **`install.sh` used the wrong Python on Macs with both Intel and Apple
  Silicon Homebrew installed.** The PATH setup always let `/usr/local/bin`
  (Intel) win over `/opt/homebrew/bin` (Apple Silicon), regardless of the
  user's own shell PATH order — so `pip install` silently ran against the
  wrong Python, producing `ModuleNotFoundError: No module named 'hatchling'`
  even with hatchling correctly installed for the right Python. Now only
  adds a Homebrew's `bin`/`sbin` to PATH if it isn't already there, so an
  already-correct shell PATH is never overridden. Also verifies after
  install that the `reaper-mcp` command on PATH actually points at the
  Python just used — catches the general version of this problem (a stale
  install from a different Python shadowing the new one) instead of just
  the Homebrew-specific case.
- **The MCP server gave a generic timeout with no explanation when run
  inside WSL.** REAPER always runs as a native Windows app — WSL has no
  GUI support for it — so if the Python server is launched from inside a
  WSL shell instead of native Windows Python, it looks for IPC files in
  WSL's own `/tmp`, a completely separate filesystem from the real
  `%TEMP%` REAPER's Lua side writes to. Every command timed out with a
  generic "server not running" message, even though REAPER and the Lua
  script were both genuinely running. Now detects WSL and raises a
  specific error explaining the actual cause instead.
- **Removed `reaper_scripts/reaper_mcp_server.eel`** — a 1700-line
  abandoned TCP-socket-on-port-9876 prototype of the server from before
  the project settled on file-based IPC. Zero references anywhere in the
  codebase, touched once at the v0.3.0 commit. Sitting in the same folder
  as the real `reaper_mcp_server.lua` with a near-identical name, it was a
  real footgun — loading the wrong script into REAPER produced an
  inexplicable silent failure with no indication why.
- **`envelope_add_points` and `midi_get_notes` had hardcoded size caps
  duplicating undocumented values.** Same drift risk as the
  `MAX_NOTES_PER_TRACK` fix below — a bare number with no named constant.
  Added `MAX_ENVELOPE_POINTS_PER_CALL` and `MAX_NOTES_READ_RESULTS` to
  `reaper_mcp_shared/constants.py` and wired both call sites to them.
- **`create_drum_pattern` / `create_chord_progression` mistimed everything
  off 60 BPM.** Both built note `start`/`end` in quarter-notes and handed
  them straight to `midi_insert_notes_batch`, which expects seconds (it
  calls `MIDI_GetPPQPosFromProjTime`, a project-seconds API). The
  auto-created item's *length* was correctly converted QN→seconds; the
  individual note positions inside it never were. At 120 BPM a pattern
  played back 2x further apart than written (a 16th-note kick pattern
  landed like 8th notes); only exactly 60 BPM happened to work, which is
  presumably why this went uncaught. Both tools now convert every note's
  start/end through `* 60.0 / bpm` before building the batch.
- **`item_split`'s reported `right_item.index` was wrong.** The Lua handler
  assumed `SplitMediaItem` inserts the new piece at `item_index + 1`, but
  like every other item-creation call in this file it actually appends to
  the end of REAPER's global item list — the file already knew this and
  worked around it correctly in `item_split_at_transients`,
  `item_split_at_positions`, and `item_duplicate`; `item_split` was the one
  handler still guessing. On any project with more than a couple of items,
  a caller trusting the returned index would silently mutate an unrelated
  item instead of the actual new split piece. Now resolves the real index
  by pointer lookup, matching the other handlers.
- **`stack_chop_layers` always read the source chop's pitch as 0.**
  `item_get_info` never returned a `pitch` field — `build_item_info` (the
  Lua struct backing every item-info response) simply didn't include the
  take's `D_PITCH`. Since the documented workflow always pitches a chop to
  a chord tone before stacking harmonies, every harmony layer came out
  detuned from the lead by however much the lead had been shifted — not an
  edge case, the normal path. Added `pitch` (and `playrate`, same call,
  same gap) to `build_item_info`'s return.
- **`item_get_source_info` / `chops_create_virtual_slice` resolved the
  wrong file for reversed or section-wrapped takes.** A SECTION or
  reversed take wraps the real audio source; reading the filename off the
  immediate take source could resolve to the wrapper object instead of
  the actual file on disk. Now walks up to the root PCM source via
  `GetMediaSourceParent` first. Also added optional `playrate`
  pass-through to `chops_create_virtual_slice` so chops stay in-tempo
  when the source material's native tempo differs from the project's.
- **`midi_insert_notes_batch` didn't validate per-note `channel`.** Every
  other numeric field (pitch, velocity, start/end) was checked; a note with
  `"channel": 20` (or negative) passed straight through to REAPER. Added
  the same 0-15 clamp `midi_insert_note` and `midi_insert_cc` already have.
- **`midi_insert_notes_batch`'s size cap didn't use the shared limit.** It
  hardcoded `50000` instead of importing `MAX_NOTES_PER_TRACK` (10000) from
  `reaper_mcp_shared/constants.py`, whose own comment says "per-track limit
  on notes in a single batch insert" — this call *is* that per-track batch
  insert. `compose_arrangement` already wires up all three shared limits
  correctly; this was the one path still using a disconnected magic number
  5x more permissive than the documented ceiling.
- **Stale docstring on `_stereo_width_fx`** (`mix_engine/master.py`) claimed
  a 0.8-1.4 → 0.5-0.85 mapping the formula doesn't implement (the code is
  self-consistent with its own "1.0 = neutral" comment; the one-line
  docstring above it was leftover from an earlier version). Corrected the
  comment to describe what the formula actually computes.
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
- **Hardening pass following a full code audit.** No API changes — all
  behaviour fixes, validation improvements, and bug fixes:
  - `mix_engine/plugins.py` — ReaVerbate dry gain was hardcoded to 1.0 on
    reverb return buses, meaning the dry signal passed through the bus
    alongside the wet tail, doubling the return level (~3 dB too loud).
    Now 0.0.
  - `mix_engine/plugins.py` — Pro-R `Decay` parameter was being fed
    `room_size`, which collapsed the decay tail when room_size was small
    and duplicated Space otherwise. Removed the redundant Decay mapping;
    Pro-R's Space already encodes decay behaviour.
  - `mix_engine/master.py` — FabFilter Pro-L 2 `Output Level` formula was
    `0.5 + true_peak_db / 60.0`, which for a target of -1 dBTP produced a
    ceiling at ~-31 dBTP (limiter barely engaged). Correct formula is
    `1.0 + true_peak_db / 60.0`, giving a ceiling at -1 dBTP as intended.
  - `mix_engine/__init__.py` — cleanup now logs every FX it removes (at
    INFO level) plus a summary count, so users can audit what
    `clean=True` did.
  - `reaper_client.py` — JSON parse-failure retries now require the
    response file's mtime to CHANGE before counting another failure.
    Previously a partial mid-write response would hit max_parse_failures
    in 150 ms even when the real response was still on its way, rejecting
    legitimate responses under heavy write contention.
  - `reaper_client.py` — `UnicodeDecodeError` is now caught and treated as
    a parse failure (same retry path), instead of propagating as an
    unhandled exception if Lua wrote a byte that wasn't valid UTF-8.
  - `reaper_mcp_server.lua` — `\uXXXX` JSON escapes are now decoded
    properly to UTF-8 (was being dropped to `?`). Track / plugin names
    with accented or CJK characters now round-trip correctly.
  - `reaper_mcp_server.lua` — directory creation no longer uses
    `os.execute` with a shell-concatenated path. Uses REAPER's native
    `RecursiveCreateDirectory` API when available (safer against
    adversarial TMPDIR values), with a defensive-quoted shell fallback
    for very old REAPER.
  - `reaper_mcp_server.lua` — added `Undo_BeginBlock` / `Undo_EndBlock`
    wrapping for every MIDI and item/track mutation that lacked it, so
    Undo history in REAPER shows readable `MCP: …` labels for every
    change the AI made.
  - `tools/patterns_tools.py` — `start_qn` was being applied twice (once
    to the auto-created item's project position and again to every note
    inside the item), so patterns appeared at 2 × start_qn instead of
    start_qn. Now notes are placed relative to the item and the item
    always starts at project 0 when auto-creating.
  - `tools/patterns_tools.py` — chord regex now accepts lowercase roots
    (`"cm7"` parses the same as `"Cm7"`). Previously lowercase chord names
    silently returned None and were listed under `failed_chords`.
  - `tools/analysis_tools.py` — `analyze_loudness` guards against silent
    audio (previously returned non-JSON `-inf` LUFS); `analyze_frequency_spectrum`
    guards against divide-by-zero when magnitudes sum to 0;
    `analyze_stereo_field` guards against divide-by-zero when either
    channel is constant/silent (was returning `NaN`, which breaks JSON
    serialisation).
  - `tools/midi_tools.py` — `midi_insert_notes_batch` now validates the
    `notes` JSON client-side: parses it, checks shape is a list, enforces
    a note-count ceiling, validates every note has pitch (0-127),
    velocity (1-127), numeric start/end with end > start.
  - `tools/compose_edit_tools.py` — the "all" sentinel for `tracks=` is
    now case-insensitive and tolerates surrounding whitespace/quotes.
  - `tool_registry.py` — warns if a profile references a module that
    isn't importable (profile definition out of sync with disk) — later
    extended to cover the default `full` profile too (see above).

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
