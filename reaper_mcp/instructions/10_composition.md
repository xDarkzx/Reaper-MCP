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
