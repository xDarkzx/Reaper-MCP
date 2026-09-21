"""Every command that changes the project leaves exactly one named undo step.

Batch and structural handlers already wrap their work in their own undo
block. Simple edits (a fader, a pan, a plugin bypass, a send, a marker...)
did not, so REAPER's undo skipped over them and rolled back some earlier
step instead. The dispatcher now records one named undo point ("MCP:
<command>") for each command in UNDO_POINT_COMMANDS that succeeded and did
not manage its own block.

Every handler that touches the project is classified as either recorded
(UNDO_POINT_COMMANDS) or deliberately exempt (UNDO_EXEMPT_COMMANDS, with a
reason), and a test fails when a new handler is added without a decision.
"""

import re
from pathlib import Path

import pytest

LUA_SRC = (
    Path(__file__).resolve().parent.parent
    / "reaper_scripts"
    / "reaper_mcp_server.lua"
)

# The same "does this handler change REAPER state" heuristic used to survey
# the bridge. Deliberately broad: a read-only handler that trips it just
# gets listed as exempt with a reason.
MUTATING_CALL = re.compile(
    r"reaper\.(?:Set\w*|Delete\w*|Insert\w*|Add\w*|Create\w*|Remove\w*|Split\w*|"
    r"Move\w*|GetSet\w*Info_String|TrackFX_(?:Set|Add|Delete|CopyToTrack|Navigate)\w*|"
    r"MIDI_(?:Set|Insert|Delete|Sort|Select)\w*|Main_OnCommand|Main_openProject|"
    r"Main_SaveProject\w*|CSurf_\w+|OnPlayButton|OnStopButton|OnPauseButton|"
    r"Track_SetSelected|Undo_DoUndo2)\("
)
HANDLER_START = re.compile(r"^function ([a-z_]+)\.([a-z_0-9]+)\(", re.M)


def _source() -> str:
    return LUA_SRC.read_text(encoding="utf-8")


def _table(source: str, name: str) -> dict:
    start = source.index(f"local {name} = {{")
    body = source[start: source.index("\n}\n", start)]
    return dict(re.findall(r'^\s*([a-z_0-9]+)\s*=\s*(true|"[^"]*")', body, re.M))


def _handlers(source: str) -> dict:
    """command name -> its source text (up to the next module-level handler)."""
    starts = [(m.start(), m.group(2)) for m in HANDLER_START.finditer(source)]
    result = {}
    for i, (pos, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(source)
        result[name] = source[pos:end]
    return result


def _classified(source: str):
    return _table(source, "UNDO_POINT_COMMANDS"), _table(source, "UNDO_EXEMPT_COMMANDS")


# ---- classification is complete and consistent ---------------------------

def test_every_mutating_handler_is_classified():
    source = _source()
    recorded, exempt = _classified(source)
    unclassified = [
        name
        for name, text in _handlers(source).items()
        if MUTATING_CALL.search(text)
        and "Undo_BeginBlock" not in text
        and name not in recorded
        and name not in exempt
    ]
    assert not unclassified, (
        "Handlers that change the project but have no undo block and no "
        f"classification: {sorted(unclassified)}. Add each to "
        "UNDO_POINT_COMMANDS (records an undo step) or UNDO_EXEMPT_COMMANDS "
        "(with a reason)."
    )


def test_classifications_name_real_handlers():
    source = _source()
    recorded, exempt = _classified(source)
    handlers = set(_handlers(source))
    assert not (set(recorded) | set(exempt)) - handlers


def test_a_command_is_never_both_recorded_and_exempt():
    recorded, exempt = _classified(_source())
    assert not set(recorded) & set(exempt)


# REAPER APIs that change items, takes and MIDI data. An undo *block* around
# these leaves an empty or missing step when called from this bridge, so a
# handler that touches them must be recorded by the dispatcher instead
# (its blocks are then kept out of REAPER; see install_block_guard).
ITEM_STATE_CALL = re.compile(
    r"reaper\.(?:MIDI_\w+|CreateNewMIDIItemInProj|AddMediaItemToTrack|DeleteTrackMediaItem|"
    r"SplitMediaItem|SetMediaItemInfo_Value|SetMediaItemTakeInfo_Value|SetMediaItemLength|"
    r"SetMediaItemPosition|InsertMedia\w*|AddTakeToMediaItem|SetActiveTake|"
    r"MoveMediaItemToTrack|GetSetMediaItemTakeInfo_String|GetSetMediaItemInfo_String)\("
)


def test_handlers_that_change_items_or_midi_are_recorded_not_left_to_a_block():
    source = _source()
    recorded, _ = _classified(source)
    read_only = ("MIDI_GetNote", "MIDI_CountEvts", "MIDI_GetCC", "MIDI_GetTextSysexEvt",
                 "MIDI_GetPPQPos", "MIDI_GetProjTimeFromPPQPos", "MIDI_GetPPQPosFromProjTime",
                 "MIDI_GetAllEvts", "MIDI_GetTrackHash", "MIDI_GetHash", "MIDI_GetScale",
                 "MIDI_GetProjQNFromPPQPos", "MIDI_GetPPQPosFromProjQN", "MIDI_GetProjTimeFromPPQPos")
    offenders = []
    for name, text in _handlers(source).items():
        if "Undo_BeginBlock" not in text or name in recorded:
            continue
        calls = [m.group(0) for m in ITEM_STATE_CALL.finditer(text)]
        if any(not any(c.startswith(f"reaper.{ro}") for ro in read_only) for c in calls):
            offenders.append(name)
    assert not offenders, (
        "These handlers change items/MIDI inside an undo block, which REAPER "
        f"does not capture: {sorted(offenders)}. Add them to UNDO_POINT_COMMANDS."
    )


# --- which REAPER call records each command's step --------------------------
# Undo_OnStateChange2 captures items, MIDI and takes; the flagged
# Undo_OnStateChangeEx2 captures everything else (track, FX, send, marker,
# tempo...). Calling both for one command can record an item change twice, so
# each command uses exactly one, chosen by what it changes.

ITEM_NAME_PREFIXES = ("item_", "midi_", "take_", "chops_")
ITEM_EXTRA_NAMES = {
    "compose_arrangement", "compose_single_track", "edit_section",
    "wipe_all_midi", "items_apply",
}
# Changes a whole track's state, which includes the items on it.
BOTH_CALLS = {"track_set_state_chunk"}
MIDI_READ_ONLY = (
    "MIDI_GetNote", "MIDI_CountEvts", "MIDI_GetCC", "MIDI_GetTextSysexEvt",
    "MIDI_GetPPQPos", "MIDI_GetProjTimeFromPPQPos", "MIDI_GetPPQPosFromProjTime",
    "MIDI_GetAllEvts", "MIDI_GetTrackHash", "MIDI_GetHash", "MIDI_GetScale",
    "MIDI_GetProjQNFromPPQPos", "MIDI_GetPPQPosFromProjQN",
)


def _changes_items(name: str, text: str) -> bool:
    calls = [m.group(0) for m in ITEM_STATE_CALL.finditer(text)]
    by_call = any(not any(c.startswith(f"reaper.{ro}") for ro in MIDI_READ_ONLY) for c in calls)
    by_name = name.startswith(ITEM_NAME_PREFIXES) or name in ITEM_EXTRA_NAMES
    return by_call or by_name


def test_every_recorded_command_that_changes_items_uses_the_item_recorder():
    source = _source()
    recorded, _ = _classified(source)
    item_commands = _table(source, "UNDO_ITEM_COMMANDS")
    handlers = _handlers(source)
    missing = [
        name for name in recorded
        if name not in BOTH_CALLS and _changes_items(name, handlers[name]) and name not in item_commands
    ]
    assert not missing, (
        f"These change items/MIDI/takes but would be recorded with the flagged call, "
        f"which does not capture them: {sorted(missing)}. Add to UNDO_ITEM_COMMANDS."
    )


def test_the_item_recorder_list_only_names_recorded_item_commands():
    source = _source()
    recorded, _ = _classified(source)
    item_commands = _table(source, "UNDO_ITEM_COMMANDS")
    handlers = _handlers(source)
    assert set(item_commands) <= set(recorded)
    wrong = [n for n in item_commands if not _changes_items(n, handlers[n])]
    assert not wrong, (
        f"These don't change items/MIDI/takes, so Undo_OnStateChange2 alone would "
        f"miss their change: {sorted(wrong)}"
    )


def _recorder(lupa):
    source = _source()
    start = source.index("local UNDO_ITEM_COMMANDS = {")
    end = source.index("\nend\n", source.index("local function record_undo_step")) + len("\nend\n")
    runtime = lupa.LuaRuntime()
    runtime.execute(
        """
        calls = {}
        reaper = {
          Undo_OnStateChange2   = function(p, n) calls[#calls+1] = "state2:" .. n end,
          Undo_OnStateChangeEx2 = function(p, n, s, t) calls[#calls+1] = "ex2:" .. n .. ":" .. s .. ":" .. t end,
        }
        """
    )
    runtime.execute(source[start:end] + "\nrecord = record_undo_step")
    record = runtime.eval("record")
    return record, lambda: list(runtime.eval("calls").values())


def test_an_item_command_is_recorded_with_the_item_call_alone():
    lupa = pytest.importorskip("lupa")
    record, calls = _recorder(lupa)
    record("midi_insert_notes_batch", "MCP: notes")
    assert calls() == ["state2:MCP: notes"]


def test_any_other_command_is_recorded_with_the_flagged_call_alone():
    lupa = pytest.importorskip("lupa")
    record, calls = _recorder(lupa)
    record("track_set_volume", "MCP: fader")
    assert calls() == ["ex2:MCP: fader:-1:-1"]


def test_replacing_a_whole_track_state_uses_both_calls():
    lupa = pytest.importorskip("lupa")
    record, calls = _recorder(lupa)
    record("track_set_state_chunk", "MCP: chunk")
    assert calls() == ["state2:MCP: chunk", "ex2:MCP: chunk:-1:-1"]


def test_no_command_is_recorded_by_both_calls_except_the_documented_one():
    source = _source()
    both = _table(source, "UNDO_BOTH_CALLS_COMMANDS")
    assert set(both) == BOTH_CALLS
    assert not set(both) & set(_table(source, "UNDO_ITEM_COMMANDS"))


def test_the_dispatcher_keeps_a_recorded_commands_blocks_out_of_reaper():
    source = _source()
    dispatch = source[source.index("local function process_command"):]
    dispatch = dispatch[: dispatch.index("local function main_loop")]
    assert "undo_commands.enter(UNDO_POINT_COMMANDS[cmd.command] == true)" in dispatch
    assert dispatch.index("undo_commands.enter(UNDO_POINT_COMMANDS") < dispatch.index("pcall(handler")


def test_every_exemption_has_a_reason():
    _, exempt = _classified(_source())
    assert exempt and all(v != "true" and len(v) > 8 for v in exempt.values())


def test_undo_and_redo_are_exempt():
    """Recording a point after an undo would erase the redo stack."""
    _, exempt = _classified(_source())
    assert "project_undo" in exempt and "project_redo" in exempt


@pytest.mark.parametrize("command", [
    "track_set_volume", "track_set_pan", "track_set_mute", "fx_enable",
    "fx_set_param", "send_set_volume", "marker_add", "item_move",
])
def test_the_everyday_edits_are_recorded(command):
    recorded, _ = _classified(_source())
    assert command in recorded


# ---- the decision function, run for real under lupa -----------------------

def _decider(lupa):
    source = _source()
    start = source.index("local UNDO_POINT_COMMANDS = {")
    end = source.index("\nend\n", source.index("local function should_record_undo_point")) + 5
    runtime = lupa.LuaRuntime()
    should = runtime.execute(source[start:end] + "\nreturn should_record_undo_point")

    def call(command, ok=True, result=True, err=None, committed=False):
        res = runtime.table_from({"x": 1}) if result is True else result
        return should(command, ok, res, err, committed)

    return call


def test_a_successful_recorded_command_gets_a_point():
    lupa = pytest.importorskip("lupa")
    assert _decider(lupa)("track_set_volume") is True


def test_a_command_that_ended_its_own_block_gets_no_second_point():
    lupa = pytest.importorskip("lupa")
    assert _decider(lupa)("track_set_volume", committed=True) is False


@pytest.mark.parametrize("kwargs", [
    {"ok": False},                # the handler threw
    {"err": "Track not found"},   # the handler reported an error
    {"result": None},             # nothing came back
])
def test_a_failed_command_leaves_no_empty_undo_step(kwargs):
    lupa = pytest.importorskip("lupa")
    assert _decider(lupa)("track_set_volume", **kwargs) is False


@pytest.mark.parametrize("command", [
    "fx_get_chain", "track_get_all", "transport_play", "project_undo",
    "project_redo", "no_such_command",
])
def test_read_only_exempt_and_unknown_commands_get_no_point(command):
    lupa = pytest.importorskip("lupa")
    assert _decider(lupa)(command) is False


# ---- wired into the dispatcher --------------------------------------------

def test_the_dispatcher_records_after_unwinding_and_before_responding():
    source = _source()
    dispatch = source[source.index("local function process_command"):]
    dispatch = dispatch[: dispatch.index("local function main_loop")]
    order = [
        dispatch.index("pcall(handler"),
        dispatch.index("unwind_open_blocks()"),
        dispatch.index("should_record_undo_point("),
        dispatch.index("pcall(record_undo_step,"),
        dispatch.index("send_success(result"),
    ]
    assert order == sorted(order)
    assert '"MCP: " .. cmd.command' in dispatch


def test_recording_a_point_can_never_break_a_command():
    source = _source()
    dispatch = source[source.index("local function process_command"):]
    assert "pcall(record_undo_step," in dispatch
