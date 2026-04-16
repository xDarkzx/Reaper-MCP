from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def send_create(source_track: int, dest_track: int) -> dict:
        """Create send between tracks. Prefer setup_routing for batch.

        Args:
            source_track: Source track index.
            dest_track: Destination track index.
        """
        if source_track < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "source_track must be >= 0")
        if dest_track < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "dest_track must be >= 0")
        if source_track == dest_track:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "Source and destination must be different tracks")
        return await client.execute("send_create", source_track=source_track, dest_track=dest_track)

    @mcp.tool()
    async def send_remove(track_index: int, send_index: int) -> dict:
        """Remove a send.

        Args:
            track_index: Source track index.
            send_index: Send index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if send_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "send_index must be >= 0")
        return await client.execute("send_remove", track_index=track_index, send_index=send_index)

    @mcp.tool()
    async def send_get_all(track_index: int) -> dict:
        """Get all sends/receives on a track.

        Args:
            track_index: Track index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        return await client.execute("send_get_all", track_index=track_index)

    @mcp.tool()
    async def send_set_volume(track_index: int, send_index: int, volume_db: float) -> dict:
        """Set send volume.

        Args:
            track_index: Source track.
            send_index: Send index.
            volume_db: dB (0=unity).
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if send_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "send_index must be >= 0")
        return await client.execute("send_set_volume", track_index=track_index,
                                    send_index=send_index, volume_db=volume_db)

    @mcp.tool()
    async def send_set_pan(track_index: int, send_index: int, pan: float) -> dict:
        """Set send pan.

        Args:
            track_index: Source track.
            send_index: Send index.
            pan: -1.0 to 1.0.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if send_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "send_index must be >= 0")
        if not -1.0 <= pan <= 1.0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Pan must be -1.0 to 1.0")
        return await client.execute("send_set_pan", track_index=track_index,
                                    send_index=send_index, pan=pan)

    @mcp.tool()
    async def send_set_mute(track_index: int, send_index: int, mute: bool) -> dict:
        """Mute/unmute send.

        Args:
            track_index: Source track.
            send_index: Send index.
            mute: True=mute.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if send_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "send_index must be >= 0")
        return await client.execute("send_set_mute", track_index=track_index,
                                    send_index=send_index, mute=mute)

    @mcp.tool()
    async def send_get_routing_diagram() -> dict:
        """Get full project routing diagram (sends, receives, outputs)."""
        return await client.execute("send_get_routing_diagram")
