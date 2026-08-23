# Mixing

## Before mixing — check what plugins the user has
Always call `fx_list_installed()` first. Returns:
- `all_installed`: every plugin in REAPER
- `best_eq`, `best_compressor`, `best_reverb`, `best_limiter`, `best_deesser`,
  `best_gate`, `best_saturator`, `best_multiband`, `best_stereo` — the
  highest-quality plugin the user has for each category. Covers FabFilter,
  Waves, iZotope, Valhalla, Softube, TDR, Slate, Melda, Soundtoys,
  Airwindows, and REAPER stock.
- `racks_detected`: any rack plugins (Waves StudioRack, Blue Cat PatchWork,
  Unfiltered Audio Lion, Kilohearts Multipass/Snap Heap). **You cannot
  configure plugins INSIDE racks** — REAPER exposes them as opaque. If the
  user wants to use modules inside a rack, they set it up manually.
- `user_overrides`: explicit category→plugin mapping from their prefs file.

**When calling `engine_mix` / `engine_master`**: the mix pipeline's built-in
calibrated param profiles only cover FabFilter + REAPER stock. For Waves /
iZotope / Valhalla etc., the pipeline adds them but uses fuzzy param-name
matching (approximate — user should fine-tune in the plugin UI afterwards).
Tell the user this.

**User can lock in preferences** via `set_fx_preferences({"eq":"...","compressor":"..."})`.
Stored in `%APPDATA%/reaper_mcp/fx_prefs.json`.

## `engine_mix(style, clean=True)` — per-track EQ + compression + reverb buses
Auto-detects FabFilter (Pro-Q 3 / Pro-C 2 / Pro-R) or falls back to REAPER stock
(ReaEQ / ReaComp / ReaVerbate).

## `engine_master(style, clean=True)` — mastering chain on master bus
HP 25Hz → bus glue comp → tonal shelf EQ → stereo width → brick-wall limiter.
Targets per-style LUFS and true-peak ceiling.

## `setup_sidechain(source_track, target_track, amount, ...)` — kick→bass/pad pumping
Creates aux send on channels 3/4, pin-maps compressor sidechain inputs, tunes the pump.
Amount 0-1: 0.4 subtle, 0.7 typical, 0.9 heavy.

## Supported styles
**EDM (11):** melodic_dubstep, big_room, future_bass, future_house, deep_house, tech_house,
progressive_house, dubstep, trap, drum_and_bass, trance

**Rock (6):** alt_rock, classic_rock, pop_rock, hard_rock, punk, post_rock

**Pop (4):** modern_pop, dance_pop, indie_pop, rnb_pop

**Electronic (4):** synthwave, lofi, ambient, hiphop

**Jazz (3):** swing_jazz, jazz_fusion, latin_jazz — near-zero bus compression,
wide dynamic range (target LUFS -13 to -16), no sidechain. Dynamics come from
the performance, not processing.

**Orchestral (3):** classical_chamber, cinematic_trailer, ambient_orchestral —
pairs with the BBC Spitfire CC reference below. No/minimal bus compression,
loudness targets -16 to -20 LUFS (closer to a classical/broadcast master than
a streaming-loudness target — that's intentional, not a bug).

**Funk/Soul (4):** classic_funk, motown_soul, neo_soul, disco_funk — fast
transient-catching compression instead of loudness-flattening compression.
Sidechain is used sparingly and never kick→bass (funk bass and kick play in
unison; ducking one under the other fights the pocket). `neo_soul` uses a
subtle vocal→keys/horns duck; `disco_funk` uses a light kick→strings duck.

Each style has genre-appropriate: LUFS target, sidechain specs, reverb character,
limiter style, and per-instrument EQ/comp curves.
