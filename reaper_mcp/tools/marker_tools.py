import json

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode
from reaper_mcp_shared.constants import MAX_LABEL_LENGTH
from reaper_mcp.tools.compose_edit_tools import _validate_color_array


def _validate_color(r: int, g: int, b: int):
    for val, name in [(r, "color_r"), (g, "color_g"), (b, "color_b")]:
        if not 0 <= val <= 255:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, f"{name} must be 0-255")


_MAX_MARKERS_APPLY_ENTRIES = 200


def _validate_markers_apply_entries(entries: list) -> None:
    if not isinstance(entries, list) or len(entries) == 0:
        raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "entries must be a non-empty JSON array")
    if len(entries) > _MAX_MARKERS_APPLY_ENTRIES:
        raise ReaperMCPError(
            ErrorCode.VALUE_OUT_OF_RANGE,
            f"Too many entries: {len(entries)} (max {_MAX_MARKERS_APPLY_ENTRIES})",
        )
    for i, entry in enumerate(entries):
        if "marker_index" not in entry:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, f"Entry {i} missing marker_index")
        marker_index = entry["marker_index"]
        if not isinstance(marker_index, int) or isinstance(marker_index, bool) or marker_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, f"Entry {i}: marker_index must be >= 0")
        if entry.get("position") is not None and entry["position"] < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, f"Entry {i}: position must be >= 0")
        if entry.get("start") is not None and entry["start"] < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, f"Entry {i}: start must be >= 0")
        if entry.get("start") is not None and entry.get("end") is not None and entry["end"] <= entry["start"]:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, f"Entry {i}: end must be greater than start")
        if entry.get("color") is not None:
            _validate_color_array(entry["color"], f"Entry {i}")
        if entry.get("name") is not None and len(entry["name"]) > MAX_LABEL_LENGTH:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, f"Entry {i}: Name too long (max {MAX_LABEL_LENGTH})")


def _order_markers_apply_entries(entries: list[dict]) -> list[dict]:
    non_deletes = [e for e in entries if e.get("delete") is not True]
    deletes = [e for e in entries if e.get("delete") is True]
    deletes.sort(key=lambda e: e["marker_index"], reverse=True)
    return non_deletes + deletes


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def marker_get_all() -> dict:
        """Get all markers and regions. For just the region list plus a cheap
        project overview, prefer project_get_overview() instead."""
        return await client.execute("marker_get_all")

    @mcp.tool()
    async def marker_add(position: float, name: str = "", color_r: int = 0, color_g: int = 0, color_b: int = 0) -> dict:
        """Add marker. Prefer add_markers_batch for multiple.

        Returns both `marker_index` and `marker_number` - use `marker_index`
        for any follow-up marker_delete/marker_edit/markers_apply call.
        `marker_number` is REAPER's own display id, which it reuses once
        freed by a delete, so it will not match `marker_index` in a project
        that's had markers deleted.

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

        Returns both `marker_index` and `region_number` - use `marker_index`
        for any follow-up marker_delete/marker_edit/markers_apply call.
        `region_number` is REAPER's own display id, which it reuses once
        freed by a delete, so it will not match `marker_index` in a project
        that's had regions deleted.

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
        """Delete marker/region. Prefer markers_apply for multiple.

        Args:
            marker_index: Index from marker_get_all.
        """
        if marker_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "marker_index must be >= 0")
        return await client.execute("marker_delete", marker_index=marker_index)

    @mcp.tool()
    async def marker_edit(marker_index: int, position: float = -1, name: str | None = None) -> dict:
        """Edit marker/region. Prefer markers_apply for multiple, or to also edit a region's end/color.

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

    @mcp.tool()
    async def markers_apply(entries: str) -> dict:
        """Batch edit (name/position/start/end/color) or delete markers and regions in one call.

        Args:
            entries: JSON array. Each: {"marker_index":0, "name":"Line 12"}.
                     Region bounds: {"marker_index":5, "start":10.0, "end":14.5}.
                     Point marker position: {"marker_index":2, "position":8.0}.
                     Color: {"marker_index":7, "color":[200,90,60]} (0-255 each).
                     Delete: {"marker_index":9, "delete":true}. Only marker_index required.
                     start/end only apply to regions, position only to point markers — a
                     mismatched field (e.g. start/end on a point marker) is silently
                     ignored, not an error. Non-delete changes apply first (in the order
                     given); deletes apply last, in descending marker_index order,
                     regardless of input order — this avoids a delete shifting the
                     indices of markers processed later in the same batch. A bad
                     marker_index is recorded in the response's errors array and does
                     not abort the rest of the batch.
        """
        try:
            parsed = json.loads(entries)
        except (json.JSONDecodeError, TypeError):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "Invalid entries JSON")
        _validate_markers_apply_entries(parsed)
        ordered = _order_markers_apply_entries(parsed)
        return await client.execute("markers_apply", entries=json.dumps(ordered))
