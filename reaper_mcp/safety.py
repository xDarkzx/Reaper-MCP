"""Auto-backup safety net for destructive operations.

Before wiping MIDI, deleting tracks/items, or applying a clean=True mix
pass, save a timestamped snapshot of the project so prior work is
recoverable even if REAPER's in-memory undo history isn't enough (its
depth is finite, and it's gone entirely if REAPER crashes or the project
gets saved over the mistake before the next manual save).
"""

import logging
import os
import time

logger = logging.getLogger(__name__)

_backed_up_this_session: set[str] = set()


async def ensure_backup(client) -> dict | None:
    """Back up the current project once per session, before a destructive
    tool runs.

    No-op if there's nothing worth protecting (a brand new, never-saved,
    or empty project) or this project's file was already backed up earlier
    in this server process's lifetime — the snapshot exists to protect what
    existed *before* the AI started working, not to re-snapshot every step.

    Never raises: a failed backup logs a warning and returns None rather
    than blocking the caller's actual operation. Refusing to act at all
    because the safety net itself failed would be a worse outcome than
    proceeding without it — REAPER's own undo history is still there.
    """
    try:
        info = await client.execute("project_get_info")
    except Exception as e:
        logger.warning("Could not check project state for auto-backup: %s", e)
        return None

    file_path = info.get("file_path", "") if isinstance(info, dict) else ""
    track_count = info.get("track_count", 0) if isinstance(info, dict) else 0
    item_count = info.get("item_count", 0) if isinstance(info, dict) else 0

    if not file_path:
        return None  # never been saved — nothing on disk to protect
    if track_count == 0 and item_count == 0:
        return None  # nothing worth protecting
    if file_path in _backed_up_this_session:
        return None  # already have a snapshot from this session

    base, ext = os.path.splitext(file_path)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = f"{base}.mcp-backup-{timestamp}{ext or '.rpp'}"

    try:
        await client.execute("project_backup", path=backup_path)
    except Exception as e:
        logger.warning("Auto-backup failed, proceeding without one: %s", e)
        return None

    _backed_up_this_session.add(file_path)
    logger.info("Auto-backed up project to %s before a destructive action", backup_path)
    return {"backup_path": backup_path}
