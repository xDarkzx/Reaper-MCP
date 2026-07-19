# Project Setup Guide

ReaperMCP gives AI full control over REAPER, but **you need VST instruments loaded on tracks** before the AI can compose. This guide explains how to set up your project for different styles of music.

> **Why can't the AI just load instruments itself?** VST instruments like Kontakt, Omnisphere, and Serum have proprietary internal browsers that REAPER's API can't access. The AI can add a VST to a track, but it can't navigate inside it to pick a specific patch (e.g., "Spitfire Violin 1 Legato"). You set up the instruments once, save as a template, and reuse it forever.

---

## Known limitation: multi-sample libraries

This applies broadly — most VST/AU instruments built around multi-sample or one-shot content (drum racks, sample-based kits, multi-sampled guitar/loop instruments) work this way, across effectively every plugin vendor. It's worth understanding up front if you're building trap, drill, hip-hop, or anything built on one-shot sample packs.

**What the AI can't see:**
- **Which sound is on which key.** A multi-sample kit with kick on one key, snare on another, hi-hat on a third — that mapping lives entirely inside the plugin's own private browser state. REAPER's automation API only exposes whatever parameters the plugin vendor chose to make automatable; per-key sample assignment isn't one of them, for any host, not just this one.
- **How each sample behaves when triggered.** Some one-shots play their full length regardless of how long you hold the key (a loop or rhythm-guitar sample, for example). Others behave like a normal instrument — held while the key is down, released when it's not. There's no way to query this either; it's authored inside the sample/patch itself.

**Why this can't be "solved" with better prompting or more MCP tools:** it isn't a gap in this project specifically — it's a hard boundary in how VST/AU plugins work. A plugin only exposes what its developer decided to expose to the host. Sample-browser internals are private by design, for every DAW, every AI, every host, always.

**Current workarounds:**
1. **Zero-setup path** — use instruments with a *published, standard* key layout instead of a custom one, so there's nothing to discover. Free examples: **MT Power Drum Kit 2** (General MIDI drum mapping — the same convention `create_drum_pattern` already assumes), or synths like **Vital**/**Surge XT** whose factory presets are browsable through REAPER's normal preset system (`fx_list_installed`, `fx_set_preset`) instead of a private in-plugin browser.
2. **Custom-kit path** — tell the AI the mapping once in plain language ("this key is snare, that one is 808, that one is hi-hat, this guitar sustains while held, that one is a one-shot loop"). That's reading labels you can already see in the plugin's own UI, not a production skill. Save it into the project notes (`project_set_notes`) so it persists across sessions.

This is a real, standing limitation, not a bug — there's no tool that reads it automatically today, and none planned unless there's real demand for it.

---

## How It Works

1. **You** set up tracks with VST instruments and patches (one-time setup)
2. **Save** the project as a REAPER template
3. **AI** calls `get_track_instruments` to see what's available
4. **AI** composes using `compose_arrangement` to write MIDI to those tracks

The AI adapts to whatever instruments you have loaded — it doesn't require specific plugins.

---

## Template: Orchestral Film/TV Scoring

This is the recommended setup for cinematic orchestral composition. Use **ensemble/section patches** for most instruments (not solo), with solo patches only for featured melodies.

### Strings (Section patches — e.g., Spitfire, CSS, Berlin Strings)

| Track | Instrument | Patch Type | Notes |
|-------|-----------|------------|-------|
| 1 | Violin 1 | Section (16 players) | Melody, highest register |
| 2 | Violin 2 | Section (14 players) | Harmony, countermelody |
| 3 | Violas | Section (12 players) | Inner voice, warmth |
| 4 | Celli | Section (10 players) | Bass voice, melody in tenor register |
| 5 | Double Basses | Section (8 players) | Foundation, lowest register |

### Brass (Section patches — e.g., Cinebrass, Berlin Brass, Spitfire)

| Track | Instrument | Patch Type | Notes |
|-------|-----------|------------|-------|
| 6 | French Horns | Section (a4 — 4 players) | The most important brass section. Warm chords, heroic melodies |
| 7 | Trumpets | Section (a2 or a3) | Fanfares, heroic themes, power |
| 8 | Trombones | Section (a3) | Power brass, dark sustained chords |
| 9 | Tuba | Solo | Bass brass, doubles basses in loud passages |

### Woodwinds (Solo patches — e.g., Cinematic Studio Woodwinds, Berlin Woodwinds)

| Track | Instrument | Patch Type | Notes |
|-------|-----------|------------|-------|
| 10 | Flute | Solo | Bright melodies, pastoral themes |
| 11 | Oboe | Solo | Emotional/pastoral solos, distinctive tone |
| 12 | Clarinet | Solo | Warm mid-range, dark low register |
| 13 | Bassoon | Solo | Bass woodwind, comedic or dark character |
| 14 | Piccolo | Solo | Used sparingly for brilliance and height |

### Percussion

| Track | Instrument | Patch Type | Notes |
|-------|-----------|------------|-------|
| 15 | Timpani | Kit or solo | Tuned percussion, rolls, accents |
| 16 | Percussion | Kit (snare, bass drum, cymbals, tam-tam) | Orchestral percussion essentials |

### Other

| Track | Instrument | Patch Type | Notes |
|-------|-----------|------------|-------|
| 17 | Harp | Solo | Arpeggios, glissandi, fairy-tale textures |
| 18 | Piano | Solo | Featured or accompaniment |
| 19 | Choir | Section (SATB) | Voices — epic moments, ethereal textures |

### Effect Buses

| Track | Purpose | Notes |
|-------|---------|-------|
| 20 | Reverb (Hall) | Large hall reverb for all instruments — the AI can set this up via `setup_effect_bus` |
| 21 | Reverb (Room) | Shorter room reverb for close/intimate sound |

> **Minimum viable orchestral template:** Strings (5 tracks) + French Horns + Trumpets + Timpani + Piano = 9 tracks. Add more as you acquire libraries.

---

## Template: Pop / Rock

| Track | Instrument | Notes |
|-------|-----------|-------|
| 1 | Drums | Drum kit plugin (EZdrummer, Superior Drummer, Addictive Drums) or MIDI mapped kit |
| 2 | Bass | Bass guitar plugin or synth bass |
| 3 | Rhythm Guitar L | Guitar amp sim or DI recording |
| 4 | Rhythm Guitar R | Panned opposite for stereo width |
| 5 | Lead Guitar / Synth | Lead melody instrument |
| 6 | Keys / Piano | Piano, Rhodes, or organ |
| 7 | Pads / Strings | Background texture |
| 8 | Lead Vocal | (for recording — leave empty for instrumental) |

---

## Template: EDM / Electronic

| Track | Instrument | Notes |
|-------|-----------|-------|
| 1 | Kick | Dedicated kick sample or synth |
| 2 | Snare / Clap | Snare and clap layers |
| 3 | Hi-hats | Closed, open, rolls |
| 4 | Percussion | Shakers, rides, toms, fills |
| 5 | Bass / 808 | Sub-bass synth (Serum, Massive, Vital) |
| 6 | Lead Synth | Main hook/melody synth |
| 7 | Pluck / Arp | Arpeggiated or plucked synth |
| 8 | Pad | Sustained atmospheric chords |
| 9 | FX | Risers, impacts, sweeps, vocal chops |

---

## Free VST Instruments

You don't need expensive libraries to get started. These are free and work well with ReaperMCP:

| Plugin | Type | Get It |
|--------|------|--------|
| **Spitfire LABS** | Orchestra, piano, strings, pads | [labs.spitfireaudio.com](https://labs.spitfireaudio.com/) |
| **BBC Symphony Orchestra Discover** | Full orchestra (free tier) | [spitfireaudio.com](https://www.spitfireaudio.com/bbc-symphony-orchestra-discover) |
| **Vital** | Wavetable synth (EDM, pop) | [vital.audio](https://vital.audio/) |
| **Dexed** | FM synth (classic DX7 sounds) | GitHub |
| **Surge XT** | Full-featured synth | [surge-synthesizer.github.io](https://surge-synthesizer.github.io/) |
| **sforzando** | SFZ sample player (plays free soundfonts) | [plogue.com](https://www.plogue.com/products/sforzando.html) |

---

## Saving as a Template

Once your project is set up with instruments:

1. **File → Save Project As Template** in REAPER
2. Give it a name like "Film Orchestra" or "EDM Production"
3. Next time, **File → Project Templates → your template name**
4. Start the Lua script, open your AI client, and compose

---

## Tips

- **Name your tracks clearly** — the AI uses track names to decide what to write (e.g., "Violin 1", not "Track 1")
- **One instrument per track** — don't stack multiple instruments on one track
- **Set initial volume/pan** — the AI can adjust these, but reasonable defaults save time
- **Keep instrument patches loaded** — if Kontakt shows "missing samples", the AI can write MIDI but you won't hear anything
- **Save often** — save the template after any instrument/routing changes so you don't lose your setup
