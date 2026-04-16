from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def transport_play() -> dict:
        """Start playback."""
        return await client.execute("transport_play")

    @mcp.tool()
    async def transport_stop() -> dict:
        """Stop playback/recording."""
        return await client.execute("transport_stop")

    @mcp.tool()
    async def transport_pause() -> dict:
        """Toggle pause."""
        return await client.execute("transport_pause")

    @mcp.tool()
    async def transport_record() -> dict:
        """Start recording."""
        return await client.execute("transport_record")

    @mcp.tool()
    async def transport_get_state() -> dict:
        """Get transport state (play/record status, position, BPM, time sig, repeat)."""
        return await client.execute("transport_get_state")

    @mcp.tool()
    async def transport_set_position(seconds: float) -> dict:
        """Set cursor position.

        Args:
            seconds: Position in seconds.
        """
        if seconds < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Position must be >= 0")
        return await client.execute("transport_set_position", seconds=seconds)

    @mcp.tool()
    async def transport_set_bpm(bpm: float) -> dict:
        """Set project tempo.

        Args:
            bpm: BPM (20-999).
        """
        if not 20 <= bpm <= 999:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "BPM must be 20-999")
        return await client.execute("transport_set_bpm", bpm=bpm)

    @mcp.tool()
    async def transport_set_time_signature(numerator: int, denominator: int) -> dict:
        """Set time signature.

        Args:
            numerator: Beats per measure (1-32).
            denominator: Beat value (1,2,4,8,16,32).
        """
        if not 1 <= numerator <= 32:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Numerator must be 1-32")
        if denominator not in (1, 2, 4, 8, 16, 32):
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Denominator must be 1,2,4,8,16,32")
        return await client.execute("transport_set_time_signature", numerator=numerator, denominator=denominator)

    @mcp.tool()
    async def transport_toggle_repeat() -> dict:
        """Toggle repeat/loop mode."""
        return await client.execute("transport_toggle_repeat")

    @mcp.tool()
    async def transport_toggle_metronome() -> dict:
        """Toggle metronome."""
        return await client.execute("transport_toggle_metronome")

    @mcp.tool()
    async def transport_set_playrate(rate: float) -> dict:
        """Set playback speed.

        Args:
            rate: 0.25-4.0 (1.0=normal).
        """
        if not 0.25 <= rate <= 4.0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Rate must be 0.25-4.0")
        return await client.execute("transport_set_playrate", rate=rate)
