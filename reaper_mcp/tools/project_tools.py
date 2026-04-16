import os
import sys

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode
from reaper_mcp_shared.constants import ALLOWED_EXPORT_FORMATS


# Directories that should never be accessed
_BLOCKED_DIRS_WIN = [
    os.environ.get("SYSTEMROOT", r"C:\Windows"),
    os.environ.get("SYSTEMDRIVE", "C:") + os.sep + "Program Files",
    os.environ.get("SYSTEMDRIVE", "C:") + os.sep + "Program Files (x86)",
]


def _safe_path(path: str) -> str:
    """Validate and normalize a file path. Blocks traversal and system directories."""
    if not path:
        raise ReaperMCPError(ErrorCode.INVALID_PATH, "Path cannot be empty")
    path = os.path.normpath(path)
    resolved = os.path.realpath(path)
    if ".." in resolved.split(os.sep):
        raise ReaperMCPError(ErrorCode.INVALID_PATH, "Path traversal not allowed")
    if not os.path.isabs(resolved):
        raise ReaperMCPError(ErrorCode.INVALID_PATH, "Path must be absolute")
    # Block system directories on Windows
    if sys.platform == "win32":
        resolved_lower = resolved.lower()
        for blocked in _BLOCKED_DIRS_WIN:
            if resolved_lower.startswith(blocked.lower()):
                raise ReaperMCPError(ErrorCode.INVALID_PATH, f"Access to system directory not allowed: {blocked}")
    return resolved


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def project_get_info() -> dict:
        """Get project info (name, BPM, time sig, tracks, length, markers, render settings)."""
        return await client.execute("project_get_info")

    @mcp.tool()
    async def project_new() -> dict:
        """Create a new empty REAPER project. Returns the new project info."""
        return await client.execute("project_new")

    @mcp.tool()
    async def project_open(path: str) -> dict:
        """Open .rpp project file.

        Args:
            path: Absolute path to .rpp file.
        """
        path = _safe_path(path)
        return await client.execute("project_open", path=path)

    @mcp.tool()
    async def project_save() -> dict:
        """Save the current project. Returns project info confirming the save."""
        return await client.execute("project_save")

    @mcp.tool()
    async def project_save_as(path: str) -> dict:
        """Save project to new path.

        Args:
            path: Absolute .rpp path.
        """
        path = _safe_path(path)
        return await client.execute("project_save_as", path=path)

    @mcp.tool()
    async def project_export_audio(path: str, format: str = "wav") -> dict:
        """Render project to audio file.

        Args:
            path: Output file path.
            format: wav, mp3, ogg, flac, or aiff.
        """
        fmt = format.lower()
        if fmt not in ALLOWED_EXPORT_FORMATS:
            raise ReaperMCPError(
                ErrorCode.INVALID_FORMAT,
                f"Format must be one of: {', '.join(sorted(ALLOWED_EXPORT_FORMATS))}",
            )
        path = _safe_path(path)
        return await client.execute_long("project_export_audio", path=path, format=fmt)

    @mcp.tool()
    async def project_undo() -> dict:
        """Undo last action."""
        return await client.execute("project_undo")

    @mcp.tool()
    async def project_redo() -> dict:
        """Redo last undone action."""
        return await client.execute("project_redo")

    @mcp.tool()
    async def project_get_notes() -> dict:
        """Get the project notes/description text."""
        return await client.execute("project_get_notes")

    @mcp.tool()
    async def project_set_notes(notes: str) -> dict:
        """Set the project notes/description text.

        Args:
            notes: The text to set as project notes (max 100 KB).
        """
        # 100 KB is plenty for notes; anything larger usually means wrong data got piped here.
        max_bytes = 100 * 1024
        if len(notes.encode("utf-8")) > max_bytes:
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE,
                f"notes too long ({len(notes)} chars) — cap is 100 KB",
            )
        return await client.execute("project_set_notes", notes=notes)

    @mcp.tool()
    async def project_set_grid(grid_division: float) -> dict:
        """Set grid division (1.0=quarter, 0.5=eighth, 0.25=sixteenth).

        Args:
            grid_division: Grid size in quarter notes.
        """
        if grid_division <= 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Grid division must be > 0")
        return await client.execute("project_set_grid", grid_division=grid_division)
