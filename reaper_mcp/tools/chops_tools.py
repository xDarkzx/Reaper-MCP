"""Vocal-chop primitives.

Building blocks for slicing, pitching, time-stretching, reversing, and
duplicating audio items in REAPER. Style-agnostic — works for vocals,
drums, FX, anything. Designed for the workflow:

    1. User loads an audio item on a track in REAPER (vocal acapella, etc.)
    2. AI calls `track_get_all` + `item_get_all` to find it.
    3. AI uses these tools to slice, repitch, sequence, layer the audio
       into a musical chop arrangement.

The artistic decisions (which slice, what pitch, what rhythm) live in the
AI. These tools do the mechanical work without imposing taste.

All tools operate on item indices the AI already has — no file loading.
"""

import json

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def item_split_at_transients(item_index: int) -> dict:
        """Slice an audio item at every detected transient.

        Uses REAPER's native transient detection (action 40310). Sensitivity
        is controlled by REAPER's project settings (Options → Preferences →
        Project → Item handling → Transient detection sensitivity), not
        by this tool — set it once in REAPER and it applies to every call.

        Args:
            item_index: Global 0-based item index of the source audio item.

        Returns:
            chops_created: number of new items created from the split.
            chops_total: total items now spanning the original time range.
            chops: list of `{item_index, position, length, offset_in_original_sec}`
                   in playback order. The AI uses these indices to repitch /
                   duplicate / reverse individual chops.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        return await client.execute("item_split_at_transients", item_index=item_index)

    @mcp.tool()
    async def item_split_at_positions(item_index: int, positions: str) -> dict:
        """Slice an item at a list of absolute project-time positions.

        For grid-based or hand-picked chopping where transient detection
        isn't right. Pass positions in seconds; positions outside the
        item's range are silently ignored.

        Args:
            item_index: Global 0-based item index.
            positions: JSON array of absolute project-time positions
                       (seconds). Example: `"[1.5, 2.0, 2.5, 3.0]"`.

        Returns the resulting chops in playback order with their indices,
        positions, lengths, and offset relative to the original item start.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        try:
            parsed = json.loads(positions)
        except json.JSONDecodeError as e:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"positions must be a JSON array: {e.msg}",
            )
        if not isinstance(parsed, list):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "positions must be a JSON array")
        if len(parsed) == 0:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "positions array is empty")
        if len(parsed) > 500:
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE,
                f"too many positions ({len(parsed)}) — max 500 per call",
            )
        for i, v in enumerate(parsed):
            if not isinstance(v, (int, float)):
                raise ReaperMCPError(
                    ErrorCode.INVALID_PARAMETER,
                    f"positions[{i}] must be numeric, got {type(v).__name__}",
                )
        return await client.execute(
            "item_split_at_positions", item_index=item_index, positions=positions,
        )

    @mcp.tool()
    async def take_set_pitch(
        item_index: int,
        semitones: float,
        take_index: int = -1,
    ) -> dict:
        """Pitch-shift a take by N semitones (no time change).

        The core of "tune a chop to a chord tone". Pass positive values to
        shift up, negative for down. Range is roughly -60 to +60 (REAPER
        clamps extremes). Half-semitone values work (`0.5`, `-1.25`, etc.)
        for fine-tuning.

        Pitch quality depends on REAPER's per-take pitch shift mode setting
        (Item Properties → Take pitch shift mode). For vocals, "Élastique
        Pro Soloist" preserves formants well. Set it once in REAPER's
        project defaults and it applies to every chop.

        Args:
            item_index: Global 0-based item index.
            semitones: Pitch shift in semitones. Float. Default 0 (no change).
            take_index: 0-based take index, or -1 for the active take.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if not -60 <= semitones <= 60:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "semitones must be in [-60, 60]")
        return await client.execute(
            "take_set_pitch",
            item_index=item_index, semitones=semitones, take_index=take_index,
        )

    @mcp.tool()
    async def take_set_playrate(
        item_index: int,
        rate: float,
        preserve_pitch: bool = True,
    ) -> dict:
        """Time-stretch a take by changing its playrate.

        With `preserve_pitch=True` (default), audio plays slower/faster
        without changing pitch — useful for fitting a chop to a beat grid.
        With `preserve_pitch=False`, this becomes a vinyl-style speed change
        (faster = higher pitch).

        After changing the rate, the item's visible length in the timeline
        does NOT auto-resize. Call `item_set_length` afterwards to match.

        Args:
            item_index: Global 0-based item index.
            rate: Playback rate. 1.0 = normal, 0.5 = half speed, 2.0 = double.
                  Range 0.05 to 16.0.
            preserve_pitch: Time-stretch without pitch change. Default True.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if not 0.05 <= rate <= 16.0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "rate must be in [0.05, 16.0]")
        return await client.execute(
            "take_set_playrate",
            item_index=item_index, rate=rate, preserve_pitch=preserve_pitch,
        )

    @mcp.tool()
    async def take_set_reversed(item_index: int) -> dict:
        """Reverse an item's audio.

        Uses REAPER's "Item: Reverse items as new take" action — the new
        reversed take becomes the active one, the original take is kept
        (item now has 2 takes). To revert, switch back to the original
        take via `item_take_set_active`.

        Useful for: reverse-cymbal-into-downbeat fills, breath-in vocal FX,
        glitchy chop reversals (Skrillex / Flume style).

        Args:
            item_index: Global 0-based item index.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        return await client.execute("take_set_reversed", item_index=item_index)

    @mcp.tool()
    async def item_duplicate(
        item_index: int,
        count: int,
        spacing_sec: float = 0.0,
    ) -> dict:
        """Copy an item N times at fixed spacing.

        Each copy is a full clone — same source, same take properties
        (pitch, playrate, FX, fades). Used for the Porter Robinson
        1/16 stutter, EDM build-up risers, percussive vocal repeats.

        With default spacing (0), copies are placed back-to-back at the
        original item's length. For tight stutters, pass a small spacing
        like `60/bpm/4` for 1/16-note repeats at the project's tempo.

        Args:
            item_index: Global 0-based source item index.
            count: Number of copies to make. Range 1-100.
            spacing_sec: Time between copy starts in seconds. 0 = use
                         item length (back-to-back). Default 0.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if not 1 <= count <= 100:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "count must be 1-100")
        if spacing_sec < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "spacing_sec must be >= 0")
        return await client.execute(
            "item_duplicate",
            item_index=item_index, count=count, spacing_sec=spacing_sec,
        )
