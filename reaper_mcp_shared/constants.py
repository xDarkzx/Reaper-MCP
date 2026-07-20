"""Shared constants: IPC paths, timeouts, and safety limits.

Limits are picked to keep REAPER responsive and avoid blocking the MCP server
for too long on any single call. Raise them carefully — Lua table construction
scales with total payload size.
"""
import os
import tempfile


def ensure_private_dir(path: str) -> None:
    """Create a directory if missing, and best-effort restrict it to the
    owning user only (0700).

    Defense against a shared multi-user Unix machine: if TMPDIR isn't set,
    IPC_DIR falls back to a bare /tmp/reaper_mcp — on a system where /tmp is
    shared across users (the Unix default), a different local user's
    reaper-mcp could otherwise read or write into these IPC files. 0700
    closes that off. Best-effort and non-fatal: if the directory already
    exists owned by a different user, this chmod attempt simply fails here
    (caught), and subsequent read/write attempts inside it will then fail
    with a normal permission error instead of silently succeeding across
    users — a safe failure, not a silent one. Largely a no-op on Windows
    (%TEMP% is already per-user by default there, and os.chmod only
    toggles the read-only attribute, not real multi-user ACLs).
    """
    os.makedirs(path, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


class Connection:
    IPC_DIR = os.path.join(tempfile.gettempdir(), "reaper_mcp")
    COMMAND_FILE = os.path.join(IPC_DIR, "command.json")
    RESPONSE_FILE = os.path.join(IPC_DIR, "response.json")
    COMMAND_TMP = os.path.join(IPC_DIR, "command.tmp")
    RESPONSE_TMP = os.path.join(IPC_DIR, "response.tmp")
    LOCK_FILE = os.path.join(IPC_DIR, "server.lock")
    # Cross-process mutex guarding one full command round-trip (write command
    # -> poll -> read response) against another reaper-mcp server process
    # doing the same at the same time. Real OS-level lock, not a kill-based
    # singleton — multiple server processes (e.g. two separate Claude
    # clients) can coexist safely; the second just waits its turn instead of
    # racing on the same command.json/response.json.
    IPC_MUTEX_FILE = os.path.join(IPC_DIR, "ipc.mutex")
    # One tiny marker file per parent client PID, holding the PID of the
    # most-recently-started server for that client. Written on startup by
    # every server; watched by every server (including itself). If a server
    # ever reads back a PID here that isn't its own, it means a newer server
    # for the same client has taken over — e.g. the client reconnected and
    # spawned a replacement without stopping this one — and it retires
    # itself. Nothing ever reads this file to kill another process; each
    # server only ever acts on what it reads about itself.
    GENERATION_DIR = os.path.join(IPC_DIR, "generations")


class Timeouts:
    POLL_INTERVAL = 0.05       # 50ms between file checks
    COMMAND = 30.0             # Default timeout for short operations
    LONG_COMMAND = 600.0       # For batch MIDI/FX writes (up to ~500KB payloads)


ALLOWED_EXPORT_FORMATS = {"wav", "mp3", "ogg", "flac", "aiff"}

# Hard ceilings for single-call operations. The Lua bridge streams JSON into a
# string buffer and parses it; very large payloads block REAPER's main thread.
# Empirically these values keep any one call under ~2 seconds on typical HW.
MAX_TRACKS = 500                 # Absolute ceiling on track index validation
MAX_LABEL_LENGTH = 1000          # Track/marker/item name max length

MAX_COMPOSE_TRACKS = 50          # Per `compose_arrangement` / `configure_tracks` call
MAX_NOTES_PER_TRACK = 10000      # Per-track limit on notes in a single batch insert
MAX_TOTAL_NOTES_PER_CALL = 50000 # Sum of notes across all tracks in one call

# Read-side context-size caps — distinct purpose from the write-side limits
# above (those protect REAPER's main thread; these protect the calling
# model's context window). Coincidentally close in magnitude to some of the
# write-side limits, but tune independently — they bound different things.
MAX_NOTES_READ_RESULTS = 10000       # `midi_get_notes` max_results ceiling
MAX_ENVELOPE_POINTS_PER_CALL = 50000 # `envelope_add_points` points-per-call ceiling
