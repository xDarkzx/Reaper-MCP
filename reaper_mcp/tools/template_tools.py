"""Track template tools — save a track's FX chain + settings to a named preset.

Templates are stored as REAPER's native track state chunks (full fidelity —
FX, sends, automation, the lot) in `%APPDATA%/reaper_mcp/track_templates/*.template`
(or `~/.reaper_mcp/track_templates/` on macOS/Linux).
"""

import logging
import os

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode

logger = logging.getLogger(__name__)


def _templates_dir() -> str:
    appdata = os.environ.get("APPDATA")
    base = os.path.join(appdata, "reaper_mcp") if appdata else os.path.join(os.path.expanduser("~"), ".reaper_mcp")
    d = os.path.join(base, "track_templates")
    os.makedirs(d, exist_ok=True)
    return d


def _safe_name(name: str) -> str:
    """Strip path separators and dangerous chars from a template name."""
    keep = "".join(c for c in name if c.isalnum() or c in " -_()")
    return keep.strip()[:120]


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def track_template_save(track_index: int, name: str) -> dict:
        """Save a track's full state (FX chain, sends, volume/pan/color, automation)
        as a named template on disk.

        Templates are stored at `%APPDATA%/reaper_mcp/track_templates/<name>.template`.

        Args:
            track_index: 0-based track index to save.
            name: Template name (letters/digits/space/`-_()` only).
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        safe = _safe_name(name)
        if not safe:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                 "name must contain at least one letter/digit")

        result = await client.execute("track_get_state_chunk", track_index=track_index)
        data = result.get("data", result)
        chunk = data.get("chunk", "")
        if not chunk:
            raise ReaperMCPError(ErrorCode.COMMAND_FAILED,
                                 "Could not read track state from REAPER")

        path = os.path.join(_templates_dir(), f"{safe}.template")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(chunk)
        except OSError as e:
            raise ReaperMCPError(ErrorCode.COMMAND_FAILED,
                                 f"Could not write template: {e}")
        return {"success": True, "path": path, "name": safe, "track_index": track_index}

    @mcp.tool()
    async def track_template_apply(name: str, track_index: int) -> dict:
        """Apply a saved template to a track — replaces its FX chain + settings.

        Args:
            name: Template name (from `track_template_list`).
            track_index: 0-based target track index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        safe = _safe_name(name)
        path = os.path.join(_templates_dir(), f"{safe}.template")
        if not os.path.exists(path):
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"Template {safe!r} not found. Run `track_template_list` to see available.",
            )
        try:
            with open(path, "r", encoding="utf-8") as f:
                chunk = f.read()
        except OSError as e:
            raise ReaperMCPError(ErrorCode.COMMAND_FAILED,
                                 f"Could not read template: {e}")
        return await client.execute(
            "track_set_state_chunk", track_index=track_index, chunk=chunk
        )

    @mcp.tool()
    async def track_template_list() -> dict:
        """List all saved track templates."""
        d = _templates_dir()
        try:
            names = sorted(
                os.path.splitext(f)[0]
                for f in os.listdir(d)
                if f.endswith(".template")
            )
        except OSError as e:
            raise ReaperMCPError(ErrorCode.COMMAND_FAILED, f"Could not list templates: {e}")
        return {"count": len(names), "templates": names, "path": d}

    @mcp.tool()
    async def track_template_delete(name: str) -> dict:
        """Delete a saved track template.

        Args:
            name: Template name to delete.
        """
        safe = _safe_name(name)
        path = os.path.join(_templates_dir(), f"{safe}.template")
        if not os.path.exists(path):
            return {"success": False, "error": f"Template {safe!r} not found"}
        try:
            os.remove(path)
        except OSError as e:
            raise ReaperMCPError(ErrorCode.COMMAND_FAILED, f"Could not delete: {e}")
        return {"success": True, "deleted": safe}
