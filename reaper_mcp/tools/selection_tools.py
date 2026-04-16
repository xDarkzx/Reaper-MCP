from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def selection_set_time(start: float, end: float) -> dict:
        """Set time selection.

        Args:
            start: Start seconds.
            end: End seconds.
        """
        if start < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Start must be >= 0")
        if end <= start:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "End must be greater than start")
        return await client.execute("selection_set_time", start=start, end=end)

    @mcp.tool()
    async def selection_get_time() -> dict:
        """Get current time selection."""
        return await client.execute("selection_get_time")

    @mcp.tool()
    async def selection_set_loop(start: float, end: float) -> dict:
        """Set loop points.

        Args:
            start: Start seconds.
            end: End seconds.
        """
        if start < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Start must be >= 0")
        if end <= start:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "End must be greater than start")
        return await client.execute("selection_set_loop", start=start, end=end)

    @mcp.tool()
    async def selection_select_all_items() -> dict:
        """Select all items."""
        return await client.execute("selection_select_all_items")

    @mcp.tool()
    async def selection_deselect_all_items() -> dict:
        """Deselect all media items."""
        return await client.execute("selection_deselect_all_items")

    @mcp.tool()
    async def selection_select_all_tracks() -> dict:
        """Select all tracks."""
        return await client.execute("selection_select_all_tracks")

    @mcp.tool()
    async def selection_deselect_all_tracks() -> dict:
        """Deselect all tracks."""
        return await client.execute("selection_deselect_all_tracks")

    @mcp.tool()
    async def selection_get_selected_tracks() -> dict:
        """Get a list of all currently selected tracks with their info."""
        return await client.execute("selection_get_selected_tracks")

    @mcp.tool()
    async def selection_get_selected_items() -> dict:
        """Get a list of all currently selected media items with their info."""
        return await client.execute("selection_get_selected_items")
