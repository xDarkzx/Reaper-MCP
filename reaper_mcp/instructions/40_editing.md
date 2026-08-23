# Editing

## `edit_section(tracks, start_time, end_time, mode)`
Replace MIDI inside a time range. Modes: `"all"` / `"notes_only"` / `"ccs_only"`.
Pass `tracks=[{"track_index":0, "notes":[...], "ccs":[...]}, ...]`.

For humanization, quantization, or scale-snapping: do it manually via `midi_set_note`,
`midi_insert_cc`, or by re-inserting notes in a batch. No automatic post-processing tools.
