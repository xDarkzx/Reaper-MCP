# CRITICAL RULES

## Working on an existing project

Most sessions are on a project that already has real work in it, not a
blank one. Before doing anything **destructive or hard-to-reverse** on a
project that already has content — wiping MIDI, deleting tracks/items, an
`engine_mix`/`engine_master` pass with `clean=True` (which removes
existing mix FX before applying new ones), or running a script via
`script_run` (its effect can't be known ahead of time — it executes
whatever the script does) — **describe what you're about to do and wait
for the user to confirm**, unless they've already given clear, specific
instruction to do exactly that action.

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
- To delete tracks, make ONE `track_delete_batch` call — `[{"all": true}]` for every track, `[{"track_index": 3}]` for one, `[{"track_indices": [0, 2, 5]}]` for several — never a loop of single deletes. It can't delete the master track. Confirm first on a project that already has content.
- NEVER use `edit_section` with empty tracks to "clear" — use `wipe_all_midi`.
- For partial wipe: `wipe_all_midi(tracks="[0,1,2]")` — pass specific track indices.
