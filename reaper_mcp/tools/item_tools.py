from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode
from reaper_mcp_shared.path_safety import safe_path as _safe_path
from reaper_mcp.safety import ensure_backup


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def item_get_all(track_index: int = -1, max_results: int = 200) -> dict:
        """Get all media items. Filter by track or -1 for all.

        Each item includes `source_file` (full path) and `source_filename`
        (basename only) for audio items — the actual dragged-in media file
        name, e.g. from a Splice/sample-pack import. Sample vendors commonly
        embed BPM/key in the filename itself ("Karra_Vocal_Loop_120bpm_Cmin.wav"),
        which the take's editable `name` field does not reliably preserve.
        Both are "" for MIDI items or items with no source.

        Args:
            track_index: Track filter (-1=all).
            max_results: Max items to return (default 200, hard ceiling 2000).
                         A chop-heavy project can have hundreds of items —
                         narrow with track_index if the result is truncated.
        """
        if max_results <= 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "max_results must be > 0")
        if max_results > 2000:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE,
                                 "max_results cannot exceed 2000 (would blow context size)")
        result = await client.execute("item_get_all", track_index=track_index)
        payload = result.get("data", result)
        items = payload.get("items", [])
        if len(items) > max_results:
            payload["items"] = items[:max_results]
            payload["truncated"] = True
            payload["returned"] = max_results
        return result

    @mcp.tool()
    async def item_get_info(item_index: int) -> dict:
        """Get detailed info for one item.

        Includes `source_file`/`source_filename` for audio items — see
        `item_get_all` for what these are and why they matter.

        Args:
            item_index: Item index.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        return await client.execute("item_get_info", item_index=item_index)

    @mcp.tool()
    async def item_select(item_index: int, selected: bool = True, exclusive: bool = False) -> dict:
        """Select/deselect an item.

        Args:
            item_index: Item index.
            selected: True=select.
            exclusive: Deselect others first.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        return await client.execute("item_select", item_index=item_index, selected=selected, exclusive=exclusive)

    @mcp.tool()
    async def item_split(item_index: int, position: float) -> dict:
        """Split item at position.

        Args:
            item_index: Item index.
            position: Split point in seconds.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if position < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Position must be >= 0")
        return await client.execute("item_split", item_index=item_index, position=position)

    @mcp.tool()
    async def item_delete(item_index: int) -> dict:
        """Delete an item.

        Args:
            item_index: Item index.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        backup = await ensure_backup(client)
        result = await client.execute("item_delete", item_index=item_index)
        if isinstance(result, dict) and backup:
            result["backup"] = backup
        return result

    @mcp.tool()
    async def item_move(item_index: int, new_position: float) -> dict:
        """Move item to new position.

        Args:
            item_index: Item index.
            new_position: New start in seconds.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if new_position < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Position must be >= 0")
        return await client.execute("item_move", item_index=item_index, new_position=new_position)

    @mcp.tool()
    async def item_set_length(item_index: int, length: float) -> dict:
        """Set item length.

        Args:
            item_index: Item index.
            length: Length in seconds.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if length <= 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Length must be > 0")
        return await client.execute("item_set_length", item_index=item_index, length=length)

    @mcp.tool()
    async def item_set_volume(item_index: int, volume_db: float) -> dict:
        """Set item volume in dB.

        Args:
            item_index: Item index.
            volume_db: dB (0=unity).
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        return await client.execute("item_set_volume", item_index=item_index, volume_db=volume_db)

    @mcp.tool()
    async def item_set_mute(item_index: int, mute: bool) -> dict:
        """Mute/unmute item.

        Args:
            item_index: Item index.
            mute: True=mute.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        return await client.execute("item_set_mute", item_index=item_index, mute=mute)

    @mcp.tool()
    async def item_set_fade(item_index: int, fade_in: float = -1, fade_out: float = -1) -> dict:
        """Set fade in/out. -1=unchanged.

        Args:
            item_index: Item index.
            fade_in: Seconds, 0 or more (-1=keep, max 60s).
            fade_out: Seconds, 0 or more (-1=keep, max 60s).
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        for label, val in (("fade_in", fade_in), ("fade_out", fade_out)):
            if val != -1 and (val < 0 or val > 60):
                raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE,
                                     f"{label} must be 0-60 seconds (or -1 to keep), got {val}")
        return await client.execute("item_set_fade", item_index=item_index, fade_in=fade_in, fade_out=fade_out)

    @mcp.tool()
    async def item_insert_media(track_index: int, path: str, position: float = 0.0) -> dict:
        """Insert audio/MIDI file into track.

        Args:
            track_index: Target track index.
            path: Absolute file path.
            position: Insert position in seconds.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if position < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Position must be >= 0")
        path = _safe_path(path)
        return await client.execute("item_insert_media", track_index=track_index, path=path, position=position)

    @mcp.tool()
    async def item_create_midi(track_index: int, position: float = 0.0, length: float = 4.0) -> dict:
        """Create an empty MIDI item on a track. Returns the item's global index.

        Args:
            track_index: 0-based track index.
            position: Item start time in seconds (>= 0).
            length: Item length in seconds (> 0).
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if position < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "position must be >= 0")
        if length <= 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "length must be > 0")
        return await client.execute("item_create_midi", track_index=track_index, position=position, length=length)

    @mcp.tool()
    async def item_move_to_track(item_index: int, dest_track_index: int) -> dict:
        """Move item to different track.

        Args:
            item_index: Item index.
            dest_track_index: Destination track index.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if dest_track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "dest_track_index must be >= 0")
        return await client.execute("item_move_to_track", item_index=item_index, dest_track_index=dest_track_index)
