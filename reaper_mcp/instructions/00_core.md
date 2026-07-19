# CRITICAL RULES

## Working on an existing project

Most sessions are on a project that already has real work in it, not a
blank one. Before doing anything **destructive or hard-to-reverse** on a
project that already has content — wiping MIDI, deleting tracks/items, or
an `engine_mix`/`engine_master` pass with `clean=True` (which removes
existing mix FX before applying new ones) — **describe what you're about
to do and wait for the user to confirm**, unless they've already given
clear, specific instruction to do exactly that action.

**Additive work does not need this** — adding new tracks, writing MIDI to
empty/new tracks, adding FX, setting up sends — proceed directly, the same
way you'd write any other composition.

This is a second layer on top of, not a replacement for, the automatic
pre-action backup those destructive tools already take internally (see
`ensure_backup` in `reaper_mcp/safety.py`) — confirm first because backups
help recovery, they don't substitute for not making an unwanted change in
the first place.

## Wiping / Clearing / Resetting
**ALWAYS use `wipe_all_midi()` to clear MIDI.** This is the ONLY correct way to wipe a project.
- It deletes MIDI items (audio items are left untouched), clears markers/regions, and resets composition state in one call.
- NEVER manually delete items with `item_delete`, `midi_delete_all_notes`, or loops of individual track operations.
- NEVER use `edit_section` with empty tracks to "clear" — use `wipe_all_midi`.
- For partial wipe: `wipe_all_midi(tracks="[0,1,2]")` — pass specific track indices.

---

# Composition Workflow (AI-driven)

You compose music directly. You choose every note, rhythm, CC curve, and keyswitch based on
the user's request and your knowledge of the genre.

## Always start here
1. `get_track_instruments()` — see what VSTi is loaded on each track. Pick targets from the list.
2. Set BPM if needed: `transport_set_bpm(bpm=...)`.
3. Plan structure (intro, verse, chorus, drop, etc.) before writing notes.
4. Write tracks one at a time, or in small batches, using the tools below.

## Writing MIDI — pick the right tool

### `compose_arrangement(tracks, clear_existing)` — small edits (≤2 tracks, ≤30 notes)
Accepts shorthand or JSON. Blocked for bigger writes — split into chunks.

### `midi_insert_notes_batch(track_index, item_index, notes)` — bulk writes on one track
JSON array of `{start, end, pitch, velocity, channel}`. Use for main writing.

### `midi_insert_note(...)` — single note (rarely needed — prefer batch)

### `midi_insert_cc(...)` — CC curves (dynamics, expression, keyswitches)
For CC1/CC11 swells, insert one CC point every ~0.1-0.25s across the swell.

**You cannot READ existing CC data.** `midi_get_ccs` has been intentionally
removed because a full CC1/CC11 dynamics track across 19 instruments would
routinely blow the context window. `analyze_score` returns note stats but
no CC data either. If the user asks "what CCs are there?", tell them you
can't read existing CCs and ask them to describe what they want — then
write fresh CC curves yourself. Use `midi_count_events` if you need to
know how many CC events exist.

## Shorthand Notation
Compact format — ~8× fewer tokens than JSON. Supported in `compose_arrangement`.

```
# Each line: TRACK_INDEX | NOTES | CC_CURVES
# Notes: NoteName:Duration:Velocity (sequential timing)
# Chords: Note+Note+Note (simultaneous)
# Rests: r:Duration  |  Time jumps: @Seconds
# Dynamics: pp/p/mp/mf/f/ff auto-generate CC1+CC11 ramps
# Raw CC: ccN:StartTime-EndTime:StartVal-EndVal
# Keyswitches: ks:0 ks:1 ks:2 ks:3 (BBC articulation switches)

3|D3:2.5:65 F3:2.5:70 A3:1.5:75 r:1.0 D3:4:80|mp:0-6,f:6-12
4|D2:8:60 r:0.5 A1:3.5:55|mp:0-12
0|ks:0 D5:2:80 F5:1:75 A5:1:85 D5:4:90|mf:0-4,ff:4-8
10|D3:4:70+A3:4:70 r:0.5 F3:3.5:75+A3:3.5:75|mp:0-8
```

Note names: C D E F G A B with # or b. C4 = middle C (MIDI 60). C3=48, C5=72.

---

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

---

# Editing

## `edit_section(tracks, start_time, end_time, mode)`
Replace MIDI inside a time range. Modes: `"all"` / `"notes_only"` / `"ccs_only"`.
Pass `tracks=[{"track_index":0, "notes":[...], "ccs":[...]}, ...]`.

For humanization, quantization, or scale-snapping: do it manually via `midi_set_note`,
`midi_insert_cc`, or by re-inserting notes in a batch. No automatic post-processing tools.

---

# BBC Spitfire CC Reference (when targeting BBC-style VSTis)
- **CC1 = Dynamics** (the important one — crossfades pp/mf/ff sample layers)
- CC7 = Volume, CC10 = Pan, CC11 = Expression (secondary volume — does NOT change tone)
- CC19 = Reverb (NOT dynamics — confirmed)
- **CC64 = Sustain pedal — NEVER on strings/winds/brass, ONLY on harp/piano/celesta**
- **Keyswitches:** KS 0=Long/Legato, KS 1=Spiccato, KS 2=Pizzicato, KS 3=Tremolo

---

# Style Cheat Sheet (short guidance)

| Family | Tips |
|--------|------|
| EDM drops | Short phrases, heavy sidechain, kick on every downbeat, sub cuts under kick via sidechain |
| Melodic dubstep | Piano + vocal chop intro → build → half-time drop with wubs. Use setup_sidechain(kick→pad, amount=0.85) |
| Rock | Guitars panned hard L/R, kick + snare centre, bass centre, vocal centre, no sidechain |
| Pop | Vocal loudest, mild bass-kick sidechain (amount 0.5), clean HP on vocals at 100Hz |
| Classical / orchestral | Strings from bar 1, CC1 the dynamics driver, no sidechain, natural dynamics |
| Ambient | Dynamic range preserved, huge reverb sends, no limiting aggression (ambient style has bus_comp=None) |
| Jazz | Write in real time-feel (swing eighths, not quantized grid), leave space for solos, brushes not sticks, no sidechain, upright bass not synth bass |
| Cinematic / trailer | Tension via slow harmonic rhythm + rising strings, percussion hits land on structural downbeats, huge headroom for the impact moments, no pumping |
| Funk | Pocket over precision — slight behind/ahead-the-beat feel per instrument, horn stabs on the "and", bass and kick lock together (never sidechain one under the other) |
| Soul | Vocal-forward, warm low-mids (don't over-HP the vocal like pop), call-and-response backing vocals, gentle compression that rides the phrasing |

Pick a target LUFS consistent with the style — engine_master handles this.
