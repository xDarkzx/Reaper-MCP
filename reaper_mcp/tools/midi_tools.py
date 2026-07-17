from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode
from reaper_mcp_shared.constants import MAX_NOTES_PER_TRACK, MAX_NOTES_READ_RESULTS


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    # ── Note Operations ──────────────────────────────────────

    @mcp.tool()
    async def midi_insert_note(
        item_index: int,
        channel: int,
        pitch: int,
        velocity: int,
        start_position: float,
        end_position: float,
    ) -> dict:
        """Insert single note into existing item. For composing use compose_arrangement.

        Args:
            item_index: MIDI item index.
            channel: 0-15.
            pitch: 0-127 (60=C4).
            velocity: 1-127.
            start_position: Start seconds.
            end_position: End seconds.
        """
        if channel < 0 or channel > 15:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Channel must be 0-15")
        if pitch < 0 or pitch > 127:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Pitch must be 0-127")
        if velocity < 1 or velocity > 127:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Velocity must be 1-127")
        if end_position <= start_position:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "end_position must be > start_position")
        return await client.execute(
            "midi_insert_note",
            item_index=item_index, channel=channel,
            pitch=pitch, velocity=velocity,
            start_position=start_position, end_position=end_position,
        )

    @mcp.tool()
    async def midi_insert_notes_batch(
        track_index: int,
        item_index: int,
        notes: str,
    ) -> dict:
        """Batch-insert notes into a MIDI item. Primary tool for writing MIDI.

        Args:
            track_index: 0-based track index.
            item_index: MIDI item index on that track.
            notes: JSON array of `{"pitch":60, "velocity":100, "start":0.0, "end":0.5, "channel":0}`.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        # Validate the JSON string before sending — the Lua side would
        # return a generic "Invalid notes JSON" error but we can catch
        # malformed structure here and give a precise reason.
        import json as _json
        try:
            parsed = _json.loads(notes)
        except _json.JSONDecodeError as e:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"`notes` is not valid JSON: {e.msg} (line {e.lineno}, col {e.colno})",
            )
        if not isinstance(parsed, list):
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"`notes` must be a JSON array, got {type(parsed).__name__}",
            )
        if len(parsed) > MAX_NOTES_PER_TRACK:
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE,
                f"Too many notes ({len(parsed)}) — split into batches ≤ {MAX_NOTES_PER_TRACK}.",
            )
        for i, n in enumerate(parsed):
            if not isinstance(n, dict):
                raise ReaperMCPError(
                    ErrorCode.INVALID_PARAMETER,
                    f"note[{i}] must be an object with pitch/velocity/start/end, got {type(n).__name__}",
                )
            for k in ("pitch", "velocity", "start", "end"):
                if k not in n:
                    raise ReaperMCPError(
                        ErrorCode.INVALID_PARAMETER,
                        f"note[{i}] is missing required key '{k}'",
                    )
            pitch, vel = n["pitch"], n["velocity"]
            if not (isinstance(pitch, (int, float)) and 0 <= pitch <= 127):
                raise ReaperMCPError(
                    ErrorCode.VALUE_OUT_OF_RANGE,
                    f"note[{i}].pitch must be 0-127, got {pitch!r}",
                )
            if not (isinstance(vel, (int, float)) and 1 <= vel <= 127):
                raise ReaperMCPError(
                    ErrorCode.VALUE_OUT_OF_RANGE,
                    f"note[{i}].velocity must be 1-127, got {vel!r}",
                )
            if not (isinstance(n["start"], (int, float)) and isinstance(n["end"], (int, float))):
                raise ReaperMCPError(
                    ErrorCode.INVALID_PARAMETER,
                    f"note[{i}] start/end must be numeric, got {type(n['start']).__name__}/{type(n['end']).__name__}",
                )
            if n["end"] <= n["start"]:
                raise ReaperMCPError(
                    ErrorCode.VALUE_OUT_OF_RANGE,
                    f"note[{i}] end ({n['end']}) must be > start ({n['start']})",
                )
            if "channel" in n and not (isinstance(n["channel"], (int, float)) and 0 <= n["channel"] <= 15):
                raise ReaperMCPError(
                    ErrorCode.VALUE_OUT_OF_RANGE,
                    f"note[{i}].channel must be 0-15, got {n['channel']!r}",
                )
        return await client.execute("midi_insert_notes_batch",
                                    track_index=track_index, item_index=item_index, notes=notes)

    @mcp.tool()
    async def midi_get_notes(item_index: int, max_results: int = 500) -> dict:
        """Get notes in a MIDI item (capped at max_results to limit context size).

        Args:
            item_index: MIDI item index.
            max_results: Max notes to return (default 500, hard ceiling 10000).
                         Use midi_count_events for total count first if unsure.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if max_results <= 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "max_results must be > 0")
        if max_results > MAX_NOTES_READ_RESULTS:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE,
                                 f"max_results cannot exceed {MAX_NOTES_READ_RESULTS} (would blow context size)")
        return await client.execute("midi_get_notes", item_index=item_index, max_results=max_results)

    @mcp.tool()
    async def midi_set_note(
        item_index: int,
        note_index: int,
        pitch: int = -1,
        velocity: int = -1,
        start_position: float = -1,
        end_position: float = -1,
        channel: int = -1,
    ) -> dict:
        """Edit existing note. -1 keeps current value.

        Args:
            item_index: MIDI item index.
            note_index: Note index in item.
            pitch: 0-127 (-1=keep).
            velocity: 1-127 (-1=keep).
            start_position: Seconds (-1=keep).
            end_position: Seconds (-1=keep).
            channel: 0-15 (-1=keep).
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if note_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "note_index must be >= 0")
        if pitch != -1 and not 0 <= pitch <= 127:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "pitch must be 0-127 (or -1 to keep)")
        if velocity != -1 and not 1 <= velocity <= 127:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "velocity must be 1-127 (or -1 to keep)")
        if channel != -1 and not 0 <= channel <= 15:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "channel must be 0-15 (or -1 to keep)")
        # Duration sanity: if both start+end are being changed, end must be > start
        if start_position != -1 and end_position != -1 and end_position <= start_position:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE,
                                 f"end_position ({end_position}) must be > start_position ({start_position})")
        return await client.execute(
            "midi_set_note",
            item_index=item_index, note_index=note_index,
            pitch=pitch, velocity=velocity,
            start_position=start_position, end_position=end_position,
            channel=channel,
        )

    @mcp.tool()
    async def midi_delete_note(item_index: int, note_index: int) -> dict:
        """Delete a note.

        Args:
            item_index: MIDI item index.
            note_index: Note index.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if note_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "note_index must be >= 0")
        return await client.execute("midi_delete_note",
                                    item_index=item_index, note_index=note_index)

    @mcp.tool()
    async def midi_select_notes(item_index: int, select_all: bool = True) -> dict:
        """Select/deselect all notes in item.

        Args:
            item_index: MIDI item index.
            select_all: True=select, False=deselect.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        return await client.execute("midi_select_notes",
                                    item_index=item_index, select_all=select_all)

    @mcp.tool()
    async def midi_delete_all_notes(item_index: int) -> dict:
        """Clear all notes from a MIDI item.

        Args:
            item_index: MIDI item index.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        return await client.execute("midi_delete_all_notes", item_index=item_index)

    # ── CC (Control Change) Operations ───────────────────────

    @mcp.tool()
    async def midi_insert_cc(
        track_index: int,
        item_index: int,
        channel: int,
        cc_number: int,
        cc_value: int,
        position: float,
    ) -> dict:
        """Insert single CC event. For composing use cc_curves in compose_arrangement or rewrite_cc.

        Args:
            track_index: 0-based track index.
            item_index: MIDI item index.
            channel: 0-15.
            cc_number: 0-127.
            cc_value: 0-127.
            position: Seconds.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if channel < 0 or channel > 15:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Channel must be 0-15")
        if cc_number < 0 or cc_number > 127:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "CC number must be 0-127")
        if cc_value < 0 or cc_value > 127:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "CC value must be 0-127")
        return await client.execute(
            "midi_insert_cc",
            track_index=track_index, item_index=item_index, channel=channel,
            cc_number=cc_number, cc_value=cc_value, position=position,
        )

    # midi_get_ccs removed — reading CC streams back would routinely blow
    # context on any dynamics-heavy arrangement (19 tracks × CC1/CC11/CC19
    # curves = thousands of events). The AI writes CCs via midi_insert_cc
    # and the shorthand parser; it doesn't need to read them back.

    @mcp.tool()
    async def midi_delete_cc(item_index: int, cc_index: int) -> dict:
        """Delete a CC event.

        Args:
            item_index: MIDI item index.
            cc_index: CC event index.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if cc_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "cc_index must be >= 0")
        return await client.execute("midi_delete_cc",
                                    item_index=item_index, cc_index=cc_index)

    # ── Utility ──────────────────────────────────────────────

    @mcp.tool()
    async def midi_get_note_names() -> dict:
        """Get MIDI note number to name mapping (C4=60, etc.)."""
        return await client.execute("midi_get_note_names")

    @mcp.tool()
    async def midi_count_events(item_index: int) -> dict:
        """Count notes, CCs, and sysex events in item.

        Args:
            item_index: MIDI item index.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        return await client.execute("midi_count_events", item_index=item_index)

    @mcp.tool()
    async def midi_sort(item_index: int) -> dict:
        """Sort MIDI events by time.

        Args:
            item_index: MIDI item index.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        return await client.execute("midi_sort", item_index=item_index)

    @mcp.tool()
    async def midi_set_item_extents(item_index: int, start_qn: float, end_qn: float) -> dict:
        """Set MIDI item boundaries in quarter notes.

        Args:
            item_index: MIDI item index.
            start_qn: Start in quarter notes.
            end_qn: End in quarter notes.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if end_qn <= start_qn:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "end_qn must be > start_qn")
        return await client.execute("midi_set_item_extents",
                                    item_index=item_index, start_qn=start_qn, end_qn=end_qn)
