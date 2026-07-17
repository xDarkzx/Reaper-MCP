"""Compose tools — granular MIDI batch insert + project inspection.

These are low-level helpers for AI-driven composition:
  - get_track_instruments: list tracks + detected VSTi
  - analyze_score: dump current MIDI data for AI to reason over
  - compose_arrangement: batch-insert notes/CCs from shorthand or JSON
                          (guarded at 2 tracks / 30 notes — for edits, not full pieces)
"""

import json
import logging
import os
import time
import glob as _glob

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode
from reaper_mcp_shared.constants import (
    MAX_COMPOSE_TRACKS, MAX_NOTES_PER_TRACK, MAX_TOTAL_NOTES_PER_CALL,
)
from reaper_mcp.tools.compose_helpers import _build_live_track_map
from reaper_mcp.shorthand import parse_shorthand, is_shorthand

logger = logging.getLogger(__name__)


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def get_track_instruments() -> dict:
        """List all tracks with detected VSTi names and item counts.

        Call this before any composition work so you know which track holds
        which instrument. Each track's `name` and VSTi are returned so you can
        pick the right track index for MIDI insertion.
        """
        result = await client.execute("get_track_instruments")
        if isinstance(result, dict) and "tracks" in result:
            live_map = _build_live_track_map(result["tracks"])
            for t in result["tracks"]:
                ti = str(t["track_index"])
                if ti in live_map:
                    t["engine_instrument"] = live_map[ti]
        return result

    @mcp.tool()
    async def analyze_score(
        tracks: str = "all",
        start_time: float = 0.0,
        end_time: float = -1.0,
    ) -> dict:
        """Dump current MIDI data: per-track notes, CCs, timing stats.

        Use this to inspect what's in the project before editing, or to verify
        what you just inserted.

        Args:
            tracks: JSON array of track indices e.g. [0,1,2], or "all".
            start_time: Start in seconds (default 0).
            end_time: End in seconds (-1 = project end).
        """
        tracks_clean = tracks.strip().strip('"').strip("'")
        if tracks_clean == "all":
            tracks = "all"
        else:
            try:
                tracks_data = json.loads(tracks)
            except (json.JSONDecodeError, TypeError):
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "Invalid tracks JSON")
            if not isinstance(tracks_data, list):
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                     "tracks must be a JSON array or 'all'")

        result = await client.execute_long(
            "analyze_score",
            tracks=tracks,
            start_time=start_time,
            end_time=end_time,
        )
        return result

    @mcp.tool()
    async def compose_arrangement(tracks: str, clear_existing: bool = False,
                                  bpm: float = 120.0) -> dict:
        """Batch-insert MIDI from shorthand or JSON — guarded for small edits only.

        Accepts either shorthand notation (e.g. `3|D3:2.5:65 E3:3.0:70|cc1:0-8:35-55`)
        or a JSON tracks array: `[{"track_index": N, "notes": [...], "ccs": [...]}]`.

        Blocked at >2 tracks or >30 total notes to prevent accidental mass inserts —
        for larger writes, call this repeatedly in smaller chunks, or use the
        batch MIDI tools directly.

        Args:
            tracks: JSON tracks array or shorthand string.
            clear_existing: True to wipe target tracks before inserting.
            bpm: Project BPM (default 120).
        """
        log_dir = os.path.join(os.environ.get("TEMP", "/tmp"), "reaper_mcp", "logs")
        try:
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, f"compose_{int(time.time())}.json")
            with open(log_path, "w", encoding="utf-8") as lf:
                lf.write(tracks)
            logs = sorted(_glob.glob(os.path.join(log_dir, "compose_*.json")))
            for old in logs[:-10]:
                try:
                    os.remove(old)
                except OSError:
                    pass  # another process may be reading — fine, try again next time
        except OSError as e:
            logger.warning("Could not write compose log: %s", e)

        state_path = os.path.join(os.environ.get("TEMP", "/tmp"), "reaper_mcp", "composed_tracks.json")

        # Detect shorthand notation (compact format)
        if is_shorthand(tracks):
            try:
                tracks_data = parse_shorthand(tracks)
            except ValueError as e:
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                     f"Shorthand parse error: {e}")
            if not tracks_data:
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                     "Shorthand notation produced no tracks")
            parsed = tracks_data
        else:
            try:
                parsed = json.loads(tracks)
            except (json.JSONDecodeError, TypeError) as e:
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                     f"Invalid JSON in tracks parameter: {e}")

        if isinstance(parsed, dict):
            tracks_data = parsed.get("tracks", [])
            if not isinstance(tracks_data, list):
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                     "Object format requires a 'tracks' array")
        elif isinstance(parsed, list):
            tracks_data = parsed
        else:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                 "tracks must be a JSON array or object with 'tracks'")

        if len(tracks_data) == 0:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "tracks array is empty")

        total_notes = sum(len(e.get("notes", [])) for e in tracks_data)
        if len(tracks_data) > 2 or total_notes > 30:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"compose_arrangement is for small edits only "
                f"({len(tracks_data)} tracks, {total_notes} notes). "
                f"Limit: ≤2 tracks, ≤30 notes. For larger writes, split into chunks "
                f"or use midi_insert_notes_batch directly."
            )

        if len(tracks_data) > MAX_COMPOSE_TRACKS:
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE,
                f"Too many tracks: {len(tracks_data)} (max {MAX_COMPOSE_TRACKS})",
            )

        seen_tracks = set()
        for i, entry in enumerate(tracks_data):
            if "track_index" not in entry:
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                     f"Track entry {i} missing track_index")
            ti = entry["track_index"]
            if not isinstance(ti, int) or ti < 0:
                raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE,
                                     f"Track entry {i}: track_index must be >= 0")
            if ti in seen_tracks:
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                     f"Duplicate track_index {ti}")
            seen_tracks.add(ti)

            notes = entry.get("notes", [])
            if len(notes) > MAX_NOTES_PER_TRACK:
                raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE,
                                     f"Track {ti}: too many notes ({len(notes)}, max {MAX_NOTES_PER_TRACK})")

        # Global cap — covers the case where shorthand expands to more notes
        # than the compose_arrangement small-edit guard suggested.
        grand_total = sum(len(e.get("notes", [])) for e in tracks_data)
        if grand_total > MAX_TOTAL_NOTES_PER_CALL:
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE,
                f"Too many notes in one call: {grand_total} (max {MAX_TOTAL_NOTES_PER_CALL}). "
                f"Split into multiple calls."
            )

        target_indices = {e["track_index"] for e in tracks_data}
        composed_set: set[int] = set()
        if os.path.exists(state_path):
            try:
                with open(state_path, "r") as sf:
                    saved_state = json.load(sf)
                if isinstance(saved_state, dict):
                    composed_set = {int(x) for x in saved_state.get("composed_tracks", [])
                                     if isinstance(x, (int, str)) and str(x).lstrip("-").isdigit()}
                elif isinstance(saved_state, list):
                    composed_set = {int(x) for x in saved_state
                                     if isinstance(x, (int, str)) and str(x).lstrip("-").isdigit()}
                else:
                    logger.warning("composed_tracks.json has unexpected type %s — treating as empty",
                                   type(saved_state).__name__)
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
                logger.warning("composed_tracks.json unreadable (%s) — treating as empty", e)
                composed_set = set()

        already_composed = target_indices & composed_set
        if already_composed and not clear_existing:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"Tracks {sorted(already_composed)} already written. "
                f"Pass clear_existing=True to overwrite."
            )

        max_ti = max(e["track_index"] for e in tracks_data)
        await client.execute("compose_ensure_tracks", max_track_index=max_ti)

        summary = []
        for entry in tracks_data:
            track_result = await client.execute_long(
                "compose_single_track",
                track_data=json.dumps(entry),
                clear_existing=clear_existing,
            )
            if isinstance(track_result, dict):
                summary.append(track_result)

        total_notes = 0
        total_ccs = 0
        track_names = []
        for s in summary:
            d = s.get("data", s) if isinstance(s, dict) else {}
            total_notes += d.get("notes_inserted", 0)
            total_ccs += d.get("ccs_inserted", 0)
            if d.get("track_name"):
                track_names.append(d["track_name"])

        result = {
            "success": True,
            "tracks_composed": len(summary),
            "total_notes": total_notes,
            "total_ccs": total_ccs,
            "tracks": track_names,
        }

        try:
            composed_set.update(target_indices)
            os.makedirs(os.path.dirname(state_path), exist_ok=True)
            with open(state_path, "w") as sf:
                json.dump({"composed_tracks": sorted(composed_set)}, sf)
        except OSError as e:
            logger.warning("Could not persist composed_tracks.json: %s", e)

        return result
