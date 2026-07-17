"""Shared constants: IPC paths, timeouts, and safety limits.

Limits are picked to keep REAPER responsive and avoid blocking the MCP server
for too long on any single call. Raise them carefully — Lua table construction
scales with total payload size.
"""
import os
import tempfile


class Connection:
    IPC_DIR = os.path.join(tempfile.gettempdir(), "reaper_mcp")
    COMMAND_FILE = os.path.join(IPC_DIR, "command.json")
    RESPONSE_FILE = os.path.join(IPC_DIR, "response.json")
    COMMAND_TMP = os.path.join(IPC_DIR, "command.tmp")
    RESPONSE_TMP = os.path.join(IPC_DIR, "response.tmp")
    LOCK_FILE = os.path.join(IPC_DIR, "server.lock")


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
