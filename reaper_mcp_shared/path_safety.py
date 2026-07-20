"""Shared file-path validation — blocks path traversal and system directories.

Used by every tool that reads or writes a file at an AI-supplied path
(project files, exported audio, inserted media, rendered-mix analysis,
sample-folder scans). Previously duplicated verbatim between item_tools.py
and project_tools.py, and missing entirely from analysis_tools.py/
loops_tools.py — consolidated here so every path-touching tool gets the
same protection instead of some having it and some not.
"""
import os
import sys

from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode

# Directories that should never be accessed
_BLOCKED_DIRS_WIN = [
    os.environ.get("SYSTEMROOT", r"C:\Windows"),
    os.environ.get("SYSTEMDRIVE", "C:") + os.sep + "Program Files",
    os.environ.get("SYSTEMDRIVE", "C:") + os.sep + "Program Files (x86)",
]
_BLOCKED_DIRS_NIX = [
    "/etc", "/bin", "/sbin", "/usr", "/boot", "/proc", "/sys", "/dev",
    "/System", "/Library",
]


def _is_blocked(resolved: str, blocked: str) -> bool:
    return resolved == blocked or resolved.startswith(blocked + os.sep)


def safe_path(path: str) -> str:
    """Validate and normalize a file path. Blocks traversal and system directories."""
    if not path:
        raise ReaperMCPError(ErrorCode.INVALID_PATH, "Path cannot be empty")
    path = os.path.normpath(path)
    resolved = os.path.realpath(path)
    if ".." in resolved.split(os.sep):
        raise ReaperMCPError(ErrorCode.INVALID_PATH, "Path traversal not allowed")
    if not os.path.isabs(resolved):
        raise ReaperMCPError(ErrorCode.INVALID_PATH, "Path must be absolute")
    # Block system directories
    if sys.platform == "win32":
        resolved_lower = resolved.lower()
        for blocked in _BLOCKED_DIRS_WIN:
            if resolved_lower.startswith(blocked.lower()):
                raise ReaperMCPError(ErrorCode.INVALID_PATH, f"Access to system directory not allowed: {blocked}")
    else:
        for blocked in _BLOCKED_DIRS_NIX:
            if _is_blocked(resolved, blocked):
                raise ReaperMCPError(ErrorCode.INVALID_PATH, f"Access to system directory not allowed: {blocked}")
    return resolved
