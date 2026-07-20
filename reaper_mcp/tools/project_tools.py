from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode
from reaper_mcp_shared.constants import ALLOWED_EXPORT_FORMATS
from reaper_mcp_shared.path_safety import safe_path as _safe_path


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def project_get_info() -> dict:
        """Get project info (name, BPM, time sig, tracks, length, markers, render settings).

        `path` is the recording/media directory (exists even for a brand
        new, never-saved project). `file_path` is the actual .rpp project
        file's path — empty string if this project has never been saved.
        """
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
        """Save project to new path. This project's active file becomes
        `path` going forward — subsequent project_save calls target it,
        not the original file. Use project_backup instead if you want a
        snapshot copy without switching your active file.

        Args:
            path: Absolute .rpp path.
        """
        path = _safe_path(path)
        return await client.execute("project_save_as", path=path)

    @mcp.tool()
    async def project_backup(path: str) -> dict:
        """Save a snapshot copy to `path` WITHOUT changing this project's
        active file — unlike project_save_as, your next project_save still
        targets the original file. Use this before a risky/destructive
        change (wiping MIDI, deleting tracks, clean=True mix passes) to
        leave a recoverable copy of what existed beforehand.

        Args:
            path: Absolute .rpp path for the backup copy.
        """
        path = _safe_path(path)
        return await client.execute("project_backup", path=path)

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
