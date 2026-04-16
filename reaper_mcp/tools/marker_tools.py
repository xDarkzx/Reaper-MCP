from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode
from reaper_mcp_shared.constants import MAX_LABEL_LENGTH


def _validate_color(r: int, g: int, b: int):
    for val, name in [(r, "color_r"), (g, "color_g"), (b, "color_b")]:
        if not 0 <= val <= 255:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, f"{name} must be 0-255")


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def marker_get_all() -> dict:
        """Get all markers and regions."""
        return await client.execute("marker_get_all")

    @mcp.tool()
    async def marker_add(position: float, name: str = "", color_r: int = 0, color_g: int = 0, color_b: int = 0) -> dict:
        """Add marker. Prefer add_markers_batch for multiple.

        Args:
            position: Seconds.
            name: Label.
            color_r: Red 0-255.
            color_g: Green 0-255.
            color_b: Blue 0-255.
        """
        if position < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Position must be >= 0")
        if len(name) > MAX_LABEL_LENGTH:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, f"Name too long (max {MAX_LABEL_LENGTH})")
        _validate_color(color_r, color_g, color_b)
        return await client.execute("marker_add", position=position, name=name,
                                    color_r=color_r, color_g=color_g, color_b=color_b)

    @mcp.tool()
    async def marker_add_region(start: float, end: float, name: str = "",
                                color_r: int = 0, color_g: int = 0, color_b: int = 0) -> dict:
        """Add region. Prefer add_markers_batch for multiple.

        Args:
            start: Start seconds.
            end: End seconds.
            name: Label.
            color_r: Red 0-255.
            color_g: Green 0-255.
            color_b: Blue 0-255.
        """
        if start < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Start must be >= 0")
        if end <= start:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "End must be greater than start")
        if len(name) > MAX_LABEL_LENGTH:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, f"Name too long (max {MAX_LABEL_LENGTH})")
        _validate_color(color_r, color_g, color_b)
        return await client.execute("marker_add_region", start=start, end=end, name=name,
                                    color_r=color_r, color_g=color_g, color_b=color_b)

    @mcp.tool()
    async def marker_delete(marker_index: int) -> dict:
        """Delete marker/region.

        Args:
            marker_index: Index from marker_get_all.
        """
        if marker_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "marker_index must be >= 0")
        return await client.execute("marker_delete", marker_index=marker_index)

    @mcp.tool()
    async def marker_edit(marker_index: int, position: float = -1, name: str | None = None) -> dict:
        """Edit marker/region.

        Args:
            marker_index: Marker index.
            position: New seconds, must be >= 0, or -1 to keep current position.
            name: New name (None=keep).
        """
        if marker_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "marker_index must be >= 0")
        # Reject negative positions other than the -1 sentinel so users don't
        # silently lose moves when they typo'd a negative number.
        if position != -1 and position < 0:
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE,
                f"position must be >= 0 or -1 to keep (got {position})",
            )
        params = {"marker_index": marker_index}
        if position >= 0:
            params["position"] = position
        if name is not None:
            if len(name) > MAX_LABEL_LENGTH:
                raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, f"Name too long (max {MAX_LABEL_LENGTH})")
            params["name"] = name
        return await client.execute("marker_edit", **params)

    @mcp.tool()
    async def marker_go_to(marker_number: int) -> dict:
        """Move cursor to marker.

        Args:
            marker_number: 1-based marker number.
        """
        if marker_number < 1:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "marker_number must be >= 1")
        return await client.execute("marker_go_to", marker_number=marker_number)
