"""Compose edit tools — wipe, reset, configure, routing, markers, edit_section, rewrite_cc, fx."""

import json
import logging

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode
from reaper_mcp_shared.constants import MAX_COMPOSE_TRACKS
from reaper_mcp.safety import ensure_backup

logger = logging.getLogger(__name__)


def _validate_color_array(color, context: str):
    """Validate the `[r, g, b]` shape used by configure_tracks/add_markers_batch
    entries — same 0-255 range check as marker_tools._validate_color, but for
    the positional-array shape rather than separate color_r/g/b args. Raises
    a clear error instead of letting a malformed value (an {r,g,b} object, a
    hex string, out-of-range floats) reach the Lua bridge, where it used to
    silently resolve to black instead of erroring.
    """
    if not isinstance(color, list) or len(color) != 3:
        raise ReaperMCPError(
            ErrorCode.INVALID_PARAMETER,
            f"{context}: color must be a [r, g, b] array of exactly 3 numbers (0-255 each)",
        )
    for val in color:
        # Whole numbers only — real RGB components are always integers 0-255.
        # This also catches the most common wrong guess: 0.0-1.0 normalized
        # floats (matching the convention several other params in this API
        # use), which would otherwise pass a bare range check and silently
        # produce near-black instead of erroring.
        is_whole_number = isinstance(val, (int, float)) and not isinstance(val, bool) and float(val).is_integer()
        if not is_whole_number or not 0 <= val <= 255:
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE,
                f"{context}: color must be a [r, g, b] array of exactly 3 whole numbers "
                f"(0-255 each) — got {val!r}",
            )


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
        import tempfile
        backup = await ensure_backup(client)
        # Reset composition state
        state_path = os.path.join(tempfile.gettempdir(),
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

        if isinstance(result, dict) and backup:
            result["backup"] = backup
        return result

    @mcp.tool()
    async def reset_composition() -> dict:
        """Unlock compose_arrangement without deleting MIDI. Use wipe_all_midi to also delete."""
        import os
        import tempfile
        state_path = os.path.join(tempfile.gettempdir(),
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
            tracks: JSON array. Each: {"track_index":0, "volume_db":-3.0, "pan":-0.5,
                    "color":[200,90,60], ...}. Only track_index required.
                    color is [r, g, b], each 0-255 (not a {"r":..} object, not a hex string).
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
            if "color" in entry and entry["color"] is not None:
                _validate_color_array(entry["color"], f"Entry {i}")

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
            markers: JSON array. Markers: {"position":0,"name":"Intro"}. Regions:
                     {"start":0,"end":8,"name":"V1","is_region":true}.
                     color optional: [r, g, b], each 0-255.
        """
        try:
            markers_data = json.loads(markers)
        except (json.JSONDecodeError, TypeError):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "Invalid markers JSON")

        if not isinstance(markers_data, list) or len(markers_data) == 0:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "markers must be a non-empty JSON array")

        if len(markers_data) > 200:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Too many markers (max 200)")

        for i, entry in enumerate(markers_data):
            if "color" in entry and entry["color"] is not None:
                _validate_color_array(entry["color"], f"Entry {i}")

        return await client.execute("add_markers_batch", markers=markers)

    @mcp.tool()
    async def rewrite_cc(
        tracks: str,
        start_time: float,
        end_time: float,
    ) -> dict:
        """Replace CC automation in a time range, leaving notes untouched.

        Write curves as explicit CC points — there are no curve templates.
        For a crescendo, insert a series of points with rising cc_value;
        the resolution is up to you (e.g. one point every half bar).

        Args:
            tracks: JSON array. Each: {"track_index":0, "ccs":[{"cc_number":1,
                    "cc_value":64, "position":0.0, "channel":0}]}. Or "all".
                    position is in seconds. Entries missing any of cc_number/
                    cc_value/position are skipped silently, so a malformed
                    array still reports success with ccs_inserted: 0 — check
                    that count rather than the success flag.
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
        """Batch add and/or configure FX across any number of tracks in one
        call — this is the tool for both "add several plugins and set their
        params" AND "set many params on FX I already added," across
        multiple tracks/bands at once. Reach for this instead of chaining
        individual fx_add/fx_set_param/fx_set_param_by_name calls — setting
        up one FabFilter Pro-Q 3 EQ band properly (Used, Enabled, Frequency,
        Gain, Shape) is 4-5 separate single-param calls done that way; here
        it's one `fx_chain` entry.

        Params are applied in a fixed, deterministic order (not raw dict
        iteration order) specifically because some plugins (confirmed:
        FabFilter Pro-Q 3/Pro-C 2) crash if a band's Used/Enabled flag isn't
        written before its other params — this already handles that, no
        need to sequence params yourself.

        Example — add the same plugin (e.g. an EQ) to 5 different tracks in
        one call, instead of 5 separate fx_add calls:
        ```json
        [
            {"track_index": 0, "fx_chain": [{"name": "FabFilter Pro-Q 3"}]},
            {"track_index": 1, "fx_chain": [{"name": "FabFilter Pro-Q 3"}]},
            {"track_index": 2, "fx_chain": [{"name": "FabFilter Pro-Q 3"}]},
            {"track_index": 3, "fx_chain": [{"name": "FabFilter Pro-Q 3"}]},
            {"track_index": 4, "fx_chain": [{"name": "FabFilter Pro-Q 3"}]}
        ]
        ```
        `fx_chain` can hold more than one plugin per track too — a whole
        Saturn + Pro-Q 3 + Pro-C 2 chain, with params, added to several
        tracks, is still one call.

        Example — set up Band 1 (Low Cut) and Band 2 (High Shelf, +2dB) on
        an EQ that's already track 0's fx_index 1, by index (skips the
        fuzzy name-matching lookup, marginally faster for a big batch):
        ```json
        [{"track_index": 0, "fx_chain": [
            {"fx_index": 1, "params_by_index": {
                "0": 1.0, "1": 1.0, "2": 0.218, "8": 0.25
            }},
            {"fx_index": 1, "params_by_index": {
                "13": 1.0, "14": 1.0, "15": 0.845, "16": 0.533, "21": 0.375
            }}
        ]}]
        ```
        (Same `fx_index` reused across entries is fine — each entry is an
        independent set of param writes, not a new FX add.)

        Args:
            tracks: JSON array, one object per track:
                `{"track_index": int, "fx_chain": [...]}`. Each `fx_chain`
                entry is one FX to add-and/or-configure:
                - `"name": str` — add new via fuzzy match (default mode).
                  `"add_mode": "find_or_add"` reuses an existing instance of
                  that plugin instead of adding a duplicate;
                  `"add_mode": "find_only"` fails if it's not already there.
                - `"fx_index": int` — target an FX that's already in the
                  chain (from an earlier fx_add/setup_fx_chain call, or
                  already present in the project) instead of adding one.
                - `"params": {name: value}` — set params by fuzzy name
                  match (e.g. `"Band 1 Frequency"`). Values 0.0-1.0
                  normalized, same as fx_set_param.
                - `"params_by_index": {"<index>": value}` — same, by exact
                  0-based param index (keys are strings — JSON object keys
                  always are). Skips the per-param name lookup.
                - `"preset": str` — load a preset by name after params are
                  applied.

        Every failure is reported per-item in the response's `summary`
        (`{"error": "..."}` on that track or that one param), never a hard
        abort of the whole batch — a bad track_index, an FX name that
        doesn't resolve, or a param name/index that doesn't match anything
        each fail on their own without losing whatever else in the same
        call succeeded. Check `summary` rather than assuming a
        non-throwing call means every item landed.
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
            except (json.JSONDecodeError, TypeError):
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "Invalid bus_color JSON")
            _validate_color_array(color_data, "bus_color")
            params["bus_color"] = bus_color

        return await client.execute("setup_effect_bus", **params)
