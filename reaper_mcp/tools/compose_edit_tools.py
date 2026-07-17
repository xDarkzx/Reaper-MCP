"""Compose edit tools — wipe, reset, configure, routing, markers, edit_section, rewrite_cc, fx."""

import json
import logging

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode
from reaper_mcp_shared.constants import MAX_COMPOSE_TRACKS

logger = logging.getLogger(__name__)


def _load_state_safe(state_path: str) -> set[int]:
    """Load composed_tracks.json and return the set of composed track indices.

    Tolerant of: missing file, malformed JSON, wrong type, partial writes.
    Returns empty set on any failure (with a logged warning).
    """
    import os
    if not os.path.exists(state_path):
        return set()
    try:
        with open(state_path, "r") as sf:
            saved_state = json.load(sf)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("composed_tracks.json unreadable (%s) — treating as empty", e)
        return set()
    if isinstance(saved_state, dict):
        entries = saved_state.get("composed_tracks", [])
    elif isinstance(saved_state, list):
        entries = saved_state
    else:
        logger.warning("composed_tracks.json has unexpected type %s — treating as empty",
                       type(saved_state).__name__)
        return set()
    try:
        return {int(x) for x in entries if isinstance(x, (int, str)) and str(x).lstrip("-").isdigit()}
    except (TypeError, ValueError) as e:
        logger.warning("composed_tracks.json entries malformed (%s) — treating as empty", e)
        return set()


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def wipe_all_midi(tracks: str = "") -> dict:
        """Wipe all MIDI items and reset composition state. Tracks can compose again after.

        Only deletes items whose active take is MIDI — audio items on the same
        tracks are left untouched. On a full wipe (tracks omitted), also clears
        all markers and regions.

        Args:
            tracks: JSON array of track indices e.g. "[0,1,2]", or empty for all.
        """
        import os
        # Reset composition state
        state_path = os.path.join(os.environ.get("TEMP", "/tmp"),
                                  "reaper_mcp", "composed_tracks.json")
        if tracks:
            # Partial wipe — remove only specified tracks from state
            composed = _load_state_safe(state_path)
            try:
                wiped = set(json.loads(tracks))
            except (json.JSONDecodeError, TypeError) as e:
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                     f"tracks must be JSON array of ints: {e}")
            composed -= wiped
            try:
                os.makedirs(os.path.dirname(state_path), exist_ok=True)
                with open(state_path, "w") as sf:
                    json.dump({"composed_tracks": sorted(composed)}, sf)
            except OSError as e:
                logger.warning("Could not write composed_tracks.json: %s", e)
        else:
            # Full wipe — clear all state
            try:
                if os.path.exists(state_path):
                    os.remove(state_path)
            except OSError as e:
                logger.warning("Could not remove composed_tracks.json: %s", e)

        params = {}
        if tracks:
            params["tracks"] = tracks
        result = await client.execute("wipe_all_midi", **params)

        # On full wipe, also clear all markers and regions
        if not tracks:
            try:
                raw = await client.execute("marker_get_all")
                if isinstance(raw, dict):
                    data = raw.get("data", raw)
                    marker_list = data.get("markers", [])
                    # Delete in reverse order to avoid index shifting
                    for m in reversed(marker_list):
                        idx = m.get("index")
                        if idx is not None:
                            await client.execute("marker_delete", marker_index=idx)
            except Exception as e:
                logger.warning("Could not clear markers on wipe: %s", e)

        return result

    @mcp.tool()
    async def reset_composition() -> dict:
        """Unlock compose_arrangement without deleting MIDI. Use wipe_all_midi to also delete."""
        import os
        state_path = os.path.join(os.environ.get("TEMP", "/tmp"),
                                  "reaper_mcp", "composed_tracks.json")
        try:
            if os.path.exists(state_path):
                os.remove(state_path)
        except OSError as e:
            logger.warning("Could not remove composed_tracks.json on reset: %s", e)
        return {"success": True, "message": "Composition state reset. "
                "compose_arrangement can now write to all tracks."}

    @mcp.tool()
    async def configure_tracks(tracks: str) -> dict:
        """Batch set volume_db, pan, color, mute, solo, name on multiple tracks.

        Args:
            tracks: JSON array. Each: {"track_index":0, "volume_db":-3.0, "pan":-0.5, ...}. Only track_index required.
        """
        try:
            tracks_data = json.loads(tracks)
        except (json.JSONDecodeError, TypeError):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "Invalid tracks JSON")

        if not isinstance(tracks_data, list) or len(tracks_data) == 0:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "tracks must be a non-empty JSON array")

        if len(tracks_data) > MAX_COMPOSE_TRACKS:
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE,
                f"Too many tracks: {len(tracks_data)} (max {MAX_COMPOSE_TRACKS})",
            )

        for i, entry in enumerate(tracks_data):
            if "track_index" not in entry:
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, f"Entry {i} missing track_index")
            if not isinstance(entry["track_index"], int) or entry["track_index"] < 0:
                raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, f"Entry {i}: track_index must be >= 0")

        return await client.execute("configure_tracks", tracks=tracks)

    @mcp.tool()
    async def setup_routing(sends: str) -> dict:
        """Batch create sends with optional volume/pan.

        Args:
            sends: JSON array. Each: {"source_track":0, "dest_track":10, "volume_db":-6.0, "pan":0.0}.
        """
        try:
            sends_data = json.loads(sends)
        except (json.JSONDecodeError, TypeError):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "Invalid sends JSON")

        if not isinstance(sends_data, list) or len(sends_data) == 0:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "sends must be a non-empty JSON array")

        for i, entry in enumerate(sends_data):
            if "source_track" not in entry or "dest_track" not in entry:
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, f"Entry {i} missing source_track or dest_track")
            if entry["source_track"] == entry["dest_track"]:
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, f"Entry {i}: source and dest must differ")

        return await client.execute("setup_routing", sends=sends)

    @mcp.tool()
    async def add_markers_batch(markers: str) -> dict:
        """Batch add markers/regions.

        Args:
            markers: JSON array. Markers: {"position":0,"name":"Intro"}. Regions: {"start":0,"end":8,"name":"V1","is_region":true}. Color optional.
        """
        try:
            markers_data = json.loads(markers)
        except (json.JSONDecodeError, TypeError):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "Invalid markers JSON")

        if not isinstance(markers_data, list) or len(markers_data) == 0:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "markers must be a non-empty JSON array")

        if len(markers_data) > 200:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Too many markers (max 200)")

        return await client.execute("add_markers_batch", markers=markers)

    @mcp.tool()
    async def rewrite_cc(
        tracks: str,
        start_time: float,
        end_time: float,
    ) -> dict:
        """Replace CC automation in a time range, leaving notes untouched. Use cc_curves templates preferred.

        Args:
            tracks: JSON array. Each: {"track_index":0, "cc_curves":[{"template":"strings_legato_warm","start":0,"end":10}]}. Or "all".
            start_time: Range start in seconds.
            end_time: Range end in seconds.
        """
        if end_time <= start_time:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "end_time must be > start_time")
        if start_time < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "start_time must be >= 0")

        # Accept "all" in any case, with or without surrounding quotes/whitespace.
        if tracks.strip().strip('"\'').lower() != "all":
            try:
                tracks_data = json.loads(tracks)
            except (json.JSONDecodeError, TypeError):
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "Invalid tracks JSON")
            if not isinstance(tracks_data, list):
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "tracks must be a JSON array or 'all'")
            tracks = json.dumps(tracks_data)
        else:
            tracks = '"all"'

        return await client.execute_long(
            "edit_section",
            tracks=tracks,
            start_time=start_time,
            end_time=end_time,
            mode="ccs_only",
        )

    @mcp.tool()
    async def edit_section(
        tracks: str,
        start_time: float,
        end_time: float,
        mode: str = "all",
        trim_item: bool = False,
    ) -> dict:
        """Clear+replace notes/CCs in a time range. For CC-only fixes, use rewrite_cc instead.

        Args:
            tracks: JSON array. Each: {"track_index":0, "notes":[...], "ccs":[...]}. Omit notes/ccs to just clear. Or "all".
            start_time: Range start in seconds.
            end_time: Range end in seconds.
            mode: "all" (default), "ccs_only", or "notes_only".
            trim_item: Shorten item to start_time (for cutting endings).
        """
        if end_time <= start_time:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "end_time must be > start_time")
        if start_time < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "start_time must be >= 0")
        if mode not in ("all", "ccs_only", "notes_only"):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                 "mode must be 'all', 'ccs_only', or 'notes_only'")

        # "all" is a special string meaning all tracks
        # Accept "all" in any case, with or without surrounding quotes/whitespace.
        if tracks.strip().strip('"\'').lower() != "all":
            try:
                tracks_data = json.loads(tracks)
            except (json.JSONDecodeError, TypeError):
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "Invalid tracks JSON")
            if not isinstance(tracks_data, list):
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "tracks must be a JSON array or 'all'")
            tracks = json.dumps(tracks_data)
        else:
            tracks = '"all"'

        return await client.execute_long(
            "edit_section",
            tracks=tracks,
            start_time=start_time,
            end_time=end_time,
            mode=mode,
            trim_item=trim_item,
        )

    @mcp.tool()
    async def setup_fx_chain(tracks: str) -> dict:
        """Batch add/configure FX across tracks. Replaces many fx_add + fx_set_param calls.

        Args:
            tracks: JSON array. Each: {"track_index":0, "fx_chain":[{"name":"ReaEQ", "params":{"Gain":0.5}, "preset":"..."}]}.
                    fx_chain modes: "name" adds new, "fx_index" targets existing, "add_mode":"find_or_add" reuses.
                    Params by name (fuzzy) or params_by_index. Values 0.0-1.0.
        """
        try:
            data = json.loads(tracks)
        except (json.JSONDecodeError, TypeError):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "Invalid tracks JSON")

        if not isinstance(data, list) or len(data) == 0:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "tracks must be a non-empty JSON array")

        for i, entry in enumerate(data):
            if "track_index" not in entry:
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, f"Entry {i} missing track_index")

        return await client.execute_long("setup_fx_chain", tracks=tracks)

    @mcp.tool()
    async def setup_effect_bus(
        bus_name: str,
        fx_chain: str,
        sends_from: str,
        bus_position: int = -1,
        bus_volume_db: float = 0.0,
        bus_color: str = "",
    ) -> dict:
        """Create effect return bus (track + FX + sends) in one call.

        Args:
            bus_name: Bus track name.
            fx_chain: JSON array of FX (same format as setup_fx_chain).
            sends_from: JSON array: [{"source_track":0, "volume_db":-6.0}].
            bus_position: Track insert position (-1 = end).
            bus_volume_db: Bus volume in dB.
            bus_color: Optional JSON color "[r,g,b]".
        """
        # Validate fx_chain
        try:
            fx_data = json.loads(fx_chain)
        except (json.JSONDecodeError, TypeError):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "Invalid fx_chain JSON")
        if not isinstance(fx_data, list):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "fx_chain must be a JSON array")

        # Validate sends_from
        try:
            sends_data = json.loads(sends_from)
        except (json.JSONDecodeError, TypeError):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "Invalid sends_from JSON")
        if not isinstance(sends_data, list):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "sends_from must be a JSON array")

        params: dict = {
            "bus_name": bus_name,
            "fx_chain": fx_chain,
            "sends_from": sends_from,
            "bus_volume_db": bus_volume_db,
        }
        if bus_position >= 0:
            params["bus_position"] = bus_position
        if bus_color:
            try:
                color_data = json.loads(bus_color)
                params["bus_color"] = bus_color
            except (json.JSONDecodeError, TypeError):
                pass

        return await client.execute("setup_effect_bus", **params)
