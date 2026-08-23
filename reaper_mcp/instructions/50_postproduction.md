# Post-Production Tools

These support dialogue/podcast/game-audio editing workflows, not just music
composition.

## Start here — `project_get_overview()`
Before doing post-production work on a project you haven't just queried,
call this first. One call gets track/item/marker counts, the region
list, `change_count`, and a selection summary — cheaper than composing
`project_get_info` + `marker_get_all` + `selection_get_*` yourself, and
it's what tells you whether you even need to re-read anything else this
turn. Only fall back to the individual tools below when you need detail
`project_get_overview()` doesn't carry (e.g. full track/item objects for
what's selected, not just indices).

## Batch item/marker edits — `items_apply` / `markers_apply`
Editing more than a couple of items or markers/regions one call at a time
is slow and burns tokens. Use these instead of looping `item_move` /
`item_set_volume` / `marker_edit` / etc.: submit a JSON array, one entry
per object, with whichever fields need to change (plus `"delete": true`
to remove it). A bad index in one entry lands in the response's `errors`
array — it doesn't abort the rest of the batch, so don't retry the whole
call over one failed entry, just look at what actually happened.

## QC pass — `analyze_silence` / `analyze_peaks` / `analyze_region_qc`
Render first (`project_export_audio`), same as the mixing analysis tools.
`analyze_region_qc` needs `marker_get_all()`'s region list passed in
directly — it does not query REAPER itself. These flag **candidates for
human review**, not confirmed defects (an intentional dramatic pause
looks identical to a bad edit to a silence detector) — report findings as
"worth checking," don't tell the user something is definitely broken.
Breath detection is not implemented (see `CHANGELOG.md` for why).

## Running the user's own scripts — `script_list` / `script_run`
`script_list` only ever sees REAPER's own Scripts folder — never suggest
or attempt to point it anywhere else. `script_run` executes arbitrary
local code: treat it like the other destructive/hard-to-reverse actions
above and confirm with the user before running a script, unless they've
already named that exact script.
