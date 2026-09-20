import json

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode
from reaper_mcp.safety import ensure_backup

_MAX_TRACK_DELETE_ENTRIES = 200
_TRACK_DELETE_SELECTORS = ("all", "track_index", "track_indices")


def _is_index(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_deletable_index(value, context: str) -> None:
    """A numbered track: an int >= 0. The master track can never be deleted."""
    if not _is_index(value):
        raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, f"{context}: track index must be an int")
    if value == -1:
        raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, f"{context}: the master track cannot be deleted")
    if value < 0:
        raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, f"{context}: track index must be >= 0")


def _normalize_track_delete_entries(entries) -> list[dict]:
    """Validate track_delete_batch entries and return them in the shape the Lua
    handler expects: either all=True or a track_indices list, highest first.

    Each entry must carry exactly one selector (all / track_index / track_indices).
    """
    if not isinstance(entries, list) or len(entries) == 0:
        raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "entries must be a non-empty JSON array")
    if len(entries) > _MAX_TRACK_DELETE_ENTRIES:
        raise ReaperMCPError(
            ErrorCode.VALUE_OUT_OF_RANGE,
            f"Too many entries: {len(entries)} (max {_MAX_TRACK_DELETE_ENTRIES})",
        )

    normalized = []
    for i, entry in enumerate(entries):
        context = f"Entry {i}"
        if not isinstance(entry, dict):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, f"{context} must be an object")
        selectors = [key for key in _TRACK_DELETE_SELECTORS if key in entry]
        if len(selectors) != 1:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"{context} needs exactly one of: {', '.join(_TRACK_DELETE_SELECTORS)}",
            )

        selector = selectors[0]
        if selector == "all":
            if entry["all"] is not True:
                raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, f"{context}: all must be true")
            normalized.append({"all": True})
        elif selector == "track_index":
            _check_deletable_index(entry["track_index"], context)
            normalized.append({"track_indices": [entry["track_index"]]})
        else:
            indices = entry["track_indices"]
            if not isinstance(indices, list) or not indices:
                raise ReaperMCPError(
                    ErrorCode.INVALID_PARAMETER,
                    f"{context}: track_indices must be a non-empty array",
                )
            for value in indices:
                _check_deletable_index(value, context)
            normalized.append({"track_indices": sorted(set(indices), reverse=True)})
    return normalized


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def track_get_all() -> dict:
        """Get all tracks with properties (name, volume, pan, mute, solo, FX, items, routing).

        Each track includes `sample_filenames` — the distinct audio file
        names actually dragged/imported onto that track (Splice, sample
        packs, etc.), not the track's own display name. Vendors commonly
        embed BPM/key in the filename itself, e.g. "Karra_Vocal_Loop_120bpm_Cmin.wav".
        Capped at 20 distinct names per track; empty if the track has no
        audio items.
        """
        return await client.execute("track_get_all")

    @mcp.tool()
    async def track_get_info(track_index: int) -> dict:
        """Get detailed info for one track.

        Includes `sample_filenames` — see `track_get_all` for what this is.

        Args:
            track_index: 0-based track index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        return await client.execute("track_get_info", track_index=track_index)

    @mcp.tool()
    async def track_create(index: int = -1, name: str = "") -> dict:
        """Create new track.

        Args:
            index: Insert position (-1 = end).
            name: Optional track name.
        """
        params = {"index": index}
        if name:
            params["name"] = name
        return await client.execute("track_create", **params)

    @mcp.tool()
    async def track_delete_batch(entries: str) -> dict:
        """Delete one track, several, or all of them, in one call.

        Destructive: on a project that already has content, confirm with the
        user before calling. A project backup is taken first.

        Args:
            entries: JSON array. Each entry has exactly one of:
                       {"all": true}                          delete every track
                       {"track_index": 3}                     delete one track
                       {"track_indices": [0, 2, 5]}           delete several
                     Indices are 0-based and refer to the track numbering as it
                     is when the call starts; deletion order is handled for you,
                     so entries can overlap or come in any order. The master
                     track can't be deleted. A bad index is recorded in the
                     response's errors array and does not abort the rest. The
                     response lists what was deleted (original index and name).
        """
        try:
            parsed = json.loads(entries)
        except (json.JSONDecodeError, TypeError):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "Invalid entries JSON")
        normalized = _normalize_track_delete_entries(parsed)
        backup = await ensure_backup(client)
        result = await client.execute("track_delete_batch", entries=json.dumps(normalized))
        if isinstance(result, dict) and backup:
            result["backup"] = backup
        return result

    @mcp.tool()
    async def track_rename(track_index: int, name: str) -> dict:
        """Rename a track.

        Args:
            track_index: 0-based track index.
            name: New name.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if not name:
            raise ReaperMCPError(ErrorCode.MISSING_PARAMETER, "Name cannot be empty")
        return await client.execute("track_rename", track_index=track_index, name=name)

    @mcp.tool()
    async def track_set_volume(track_index: int, volume_db: float) -> dict:
        """Set track volume. Prefer configure_tracks for batch.

        Args:
            track_index: 0-based track index.
            volume_db: Volume in dB (0=unity, -6=half).
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        return await client.execute("track_set_volume", track_index=track_index, volume_db=volume_db)

    @mcp.tool()
    async def track_set_pan(track_index: int, pan: float) -> dict:
        """Set track pan. Prefer configure_tracks for batch.

        Args:
            track_index: 0-based track index.
            pan: -1.0 (left) to 1.0 (right).
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if not -1.0 <= pan <= 1.0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Pan must be -1.0 to 1.0")
        return await client.execute("track_set_pan", track_index=track_index, pan=pan)

    @mcp.tool()
    async def track_set_mute(track_index: int, mute: bool) -> dict:
        """Mute/unmute a track.

        Args:
            track_index: 0-based track index.
            mute: True=mute, False=unmute.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        return await client.execute("track_set_mute", track_index=track_index, mute=mute)

    @mcp.tool()
    async def track_set_solo(track_index: int, solo: bool) -> dict:
        """Solo/unsolo a track.

        Args:
            track_index: 0-based track index.
            solo: True=solo, False=unsolo.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        return await client.execute("track_set_solo", track_index=track_index, solo=solo)

    @mcp.tool()
    async def track_set_record_arm(track_index: int, arm: bool) -> dict:
        """Arm/disarm track for recording.

        Args:
            track_index: 0-based track index.
            arm: True=arm, False=disarm.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        return await client.execute("track_set_record_arm", track_index=track_index, arm=arm)

    @mcp.tool()
    async def track_set_color(track_index: int, r: int, g: int, b: int) -> dict:
        """Set track color (RGB 0-255). Prefer configure_tracks for batch.

        Args:
            track_index: 0-based track index.
            r: Red 0-255.
            g: Green 0-255.
            b: Blue 0-255.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        for val, name in [(r, "r"), (g, "g"), (b, "b")]:
            if not 0 <= val <= 255:
                raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, f"{name} must be 0-255")
        return await client.execute("track_set_color", track_index=track_index, r=r, g=g, b=b)

    @mcp.tool()
    async def track_select(track_index: int, selected: bool = True, exclusive: bool = False) -> dict:
        """Select/deselect a track.

        Args:
            track_index: 0-based track index.
            selected: True=select.
            exclusive: Deselect others first.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        return await client.execute("track_select", track_index=track_index, selected=selected, exclusive=exclusive)

    @mcp.tool()
    async def track_set_input(track_index: int, input_index: int) -> dict:
        """Set recording input. 0=none, 1-1024=mono, 1024+=stereo, 4096+=MIDI, -1=MIDI all.

        Args:
            track_index: 0-based track index.
            input_index: Input channel index. Valid values: -1 (MIDI all inputs), or >= 0.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if input_index != -1 and input_index < 0:
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE,
                f"input_index must be -1 (MIDI all) or >= 0, got {input_index}",
            )
        return await client.execute("track_set_input", track_index=track_index, input_index=input_index)

    @mcp.tool()
    async def track_get_mixer_state() -> dict:
        """Get mixer state for all tracks (volumes, pans, mutes, solos, sends)."""
        return await client.execute("track_get_mixer_state")

    @mcp.tool()
    async def track_get_peak(track_index: int) -> dict:
        """Read instantaneous peak level from a track's meter (L + R channels).

        Returns peak in both linear gain (0-1+) and dB (-144 to +12 or so).
        **Only meaningful DURING playback** — REAPER's meters only report
        when audio is passing through. Start playback, wait a moment, then read.

        Useful for: checking if a track is clipping, comparing levels between
        tracks, verifying a mix isn't too hot.

        Returns:
            `{peak_l_db, peak_r_db, peak_max_db, peak_l_linear, peak_r_linear}`

        Args:
            track_index: 0-based track index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        return await client.execute("track_get_peak", track_index=track_index)

    @mcp.tool()
    async def track_freeze(track_index: int) -> dict:
        """Freeze a track to stereo audio (pre-fader render of FX + VSTi).

        Uses REAPER action 41223. Freezing bypasses the live FX chain and
        plays back rendered audio — use when a track's VSTi or FX chain
        is CPU-heavy and you're done editing that part.

        Call `track_unfreeze` to restore the original FX + MIDI state.

        Args:
            track_index: 0-based track index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        return await client.execute("track_freeze", track_index=track_index)

    @mcp.tool()
    async def track_unfreeze(track_index: int) -> dict:
        """Unfreeze a track, restoring its original FX chain and MIDI state.

        Uses REAPER action 41644.

        Args:
            track_index: 0-based track index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        return await client.execute("track_unfreeze", track_index=track_index)

    @mcp.tool()
    async def track_set_folder(track_index: int, folder_depth: int) -> dict:
        """Set folder state. 0=normal, 1=folder parent, -1=last in folder.

        Args:
            track_index: 0-based track index.
            folder_depth: Folder depth value.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        return await client.execute("track_set_folder", track_index=track_index, folder_depth=folder_depth)
