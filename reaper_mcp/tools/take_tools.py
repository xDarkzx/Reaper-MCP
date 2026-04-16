"""Take management tools — multiple takes per item (vocal comping, alternate MIDI performances)."""

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def item_take_list(item_index: int) -> dict:
        """List all takes on an item with their active status.

        Useful for vocal comping (multiple vocal passes as separate takes on
        one item) or alternate MIDI performances.

        Args:
            item_index: Global item index.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        return await client.execute("item_take_list", item_index=item_index)

    @mcp.tool()
    async def item_take_set_active(item_index: int, take_index: int) -> dict:
        """Switch which take plays back on an item.

        Args:
            item_index: Global item index.
            take_index: 0-based take index (from `item_take_list`).
        """
        if item_index < 0 or take_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "indices must be >= 0")
        return await client.execute("item_take_set_active",
                                    item_index=item_index, take_index=take_index)

    @mcp.tool()
    async def item_take_add(item_index: int) -> dict:
        """Add a new empty take to an item. Returns the new take's index.

        Args:
            item_index: Global item index.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        return await client.execute("item_take_add", item_index=item_index)

    @mcp.tool()
    async def item_take_delete_active(item_index: int) -> dict:
        """Delete the currently active take from an item.

        To delete a non-active take, first call `item_take_set_active` on it.

        Args:
            item_index: Global item index.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        return await client.execute("item_take_delete_active", item_index=item_index)
