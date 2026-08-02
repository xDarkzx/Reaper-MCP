from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def fx_add(track_index: int, fx_name: str) -> dict:
        """Add FX plugin to track. Prefer setup_fx_chain for batch operations.

        The name is passed straight to REAPER's TrackFX_AddByName, which
        resolves it fuzzily. Plugin format cannot be selected: pass the bare
        name only. The display prefixes from fx_list_installed ("VSTi: ",
        "VST3i: ") are not format selectors — they are matched as part of the
        fuzzy string and silently resolve to whichever format REAPER prefers,
        normally VST3. REAPER's own "vst:"/"vst3:" prefixes and the raw .dll
        filename both fail outright with FX not found. So when a plugin is
        installed as both VST2 and VST3, fx_list_installed will list both but
        only one is reachable here.

        Args:
            track_index: 0-based track index.
            fx_name: Bare plugin name (e.g. "ReaEQ", "ReaComp", "ARIA Player").
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if not fx_name:
            raise ReaperMCPError(ErrorCode.MISSING_PARAMETER, "fx_name cannot be empty")
        return await client.execute("fx_add", track_index=track_index, fx_name=fx_name)

    @mcp.tool()
    async def fx_remove(track_index: int, fx_index: int) -> dict:
        """Remove FX from track chain.

        Args:
            track_index: 0-based track index.
            fx_index: 0-based FX chain index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if fx_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "fx_index must be >= 0")
        return await client.execute("fx_remove", track_index=track_index, fx_index=fx_index)

    @mcp.tool()
    async def fx_get_chain(track_index: int) -> dict:
        """Get FX chain for a track (names, enabled, presets, param counts).

        Args:
            track_index: 0-based track index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        return await client.execute("fx_get_chain", track_index=track_index)

    @mcp.tool()
    async def fx_get_params(track_index: int, fx_index: int) -> dict:
        """Get all parameters of an FX plugin (names, values, formatted display).

        Automatically filters out junk params (Internal, MIDI CC, unused FabFilter bands)
        to keep context size small.

        Args:
            track_index: 0-based track index.
            fx_index: 0-based FX chain index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if fx_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "fx_index must be >= 0")
        return await client.execute("fx_get_params", track_index=track_index, fx_index=fx_index)

    @mcp.tool()
    async def fx_set_param(track_index: int, fx_index: int, param_index: int, value: float) -> dict:
        """Set FX parameter by index. Prefer setup_fx_chain for batch operations.

        Args:
            track_index: 0-based track index.
            fx_index: 0-based FX chain index.
            param_index: 0-based parameter index.
            value: 0.0-1.0 normalized.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if fx_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "fx_index must be >= 0")
        if param_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "param_index must be >= 0")
        if not 0.0 <= value <= 1.0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Value must be 0.0 to 1.0")
        return await client.execute(
            "fx_set_param",
            track_index=track_index, fx_index=fx_index,
            param_index=param_index, value=value,
        )

    @mcp.tool()
    async def fx_set_param_by_name(track_index: int, fx_index: int, param_name: str, value: float) -> dict:
        """Set FX parameter by name (fuzzy match).

        Args:
            track_index: 0-based track index.
            fx_index: 0-based FX chain index.
            param_name: Parameter name or partial match.
            value: 0.0-1.0 normalized.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if fx_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "fx_index must be >= 0")
        if not param_name:
            raise ReaperMCPError(ErrorCode.MISSING_PARAMETER, "param_name cannot be empty")
        if not 0.0 <= value <= 1.0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Value must be 0.0 to 1.0")
        return await client.execute(
            "fx_set_param_by_name",
            track_index=track_index, fx_index=fx_index,
            param_name=param_name, value=value,
        )

    @mcp.tool()
    async def fx_enable(track_index: int, fx_index: int) -> dict:
        """Enable an FX plugin.

        Args:
            track_index: 0-based track index.
            fx_index: 0-based FX chain index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if fx_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "fx_index must be >= 0")
        return await client.execute("fx_enable", track_index=track_index, fx_index=fx_index)

    @mcp.tool()
    async def fx_disable(track_index: int, fx_index: int) -> dict:
        """Bypass an FX plugin.

        Args:
            track_index: 0-based track index.
            fx_index: 0-based FX chain index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if fx_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "fx_index must be >= 0")
        return await client.execute("fx_disable", track_index=track_index, fx_index=fx_index)

    @mcp.tool()
    async def fx_show_ui(track_index: int, fx_index: int) -> dict:
        """Open FX plugin UI window.

        Args:
            track_index: 0-based track index.
            fx_index: 0-based FX chain index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if fx_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "fx_index must be >= 0")
        return await client.execute("fx_show_ui", track_index=track_index, fx_index=fx_index)

    @mcp.tool()
    async def fx_get_preset(track_index: int, fx_index: int) -> dict:
        """Get current preset name and count.

        Args:
            track_index: 0-based track index.
            fx_index: 0-based FX chain index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if fx_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "fx_index must be >= 0")
        return await client.execute("fx_get_preset", track_index=track_index, fx_index=fx_index)

    @mcp.tool()
    async def fx_set_preset(
        track_index: int,
        fx_index: int,
        preset_name: str,
        include_params: bool = False,
    ) -> dict:
        """Load preset by name. Returns the resulting preset, not the parameters.

        The name must match the plugin's own spelling. Some plugins report
        names padded to a fixed width (e.g. KORG TRINITY pads to 16 chars),
        and the padded form is what has to be passed. Take the name from
        fx_get_preset or fx_navigate_preset rather than from REAPER's
        presets/*.ini, which stores it trimmed.

        If the preset does not actually change, this raises instead of
        reporting success.

        Args:
            track_index: 0-based track index.
            fx_index: 0-based FX chain index.
            preset_name: Preset name, exactly as the plugin reports it.
            include_params: Also return the plugin's full parameter list.
                Off by default — on large instruments that runs to tens of
                thousands of characters. Use fx_get_params when the
                parameters are what you actually want.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if fx_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "fx_index must be >= 0")
        if not preset_name:
            raise ReaperMCPError(ErrorCode.MISSING_PARAMETER, "preset_name cannot be empty")
        return await client.execute(
            "fx_set_preset",
            track_index=track_index,
            fx_index=fx_index,
            preset_name=preset_name,
            include_params=include_params,
        )

    @mcp.tool()
    async def fx_navigate_preset(track_index: int, fx_index: int, direction: int) -> dict:
        """Step to next/previous preset.

        Args:
            track_index: 0-based track index.
            fx_index: 0-based FX chain index.
            direction: 1=next, -1=previous.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if fx_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "fx_index must be >= 0")
        if direction not in (-1, 1):
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Direction must be 1 (next) or -1 (previous)")
        return await client.execute("fx_navigate_preset", track_index=track_index, fx_index=fx_index, direction=direction)

    @mcp.tool()
    async def fx_get_instrument(track_index: int) -> dict:
        """Find VSTi instrument on track. Returns index + params, or -1 if none.

        Args:
            track_index: 0-based track index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        return await client.execute("fx_get_instrument", track_index=track_index)

    @mcp.tool()
    async def fx_move(track_index: int, fx_index: int, new_index: int) -> dict:
        """Move FX to different position in chain.

        Args:
            track_index: 0-based track index.
            fx_index: Current FX index.
            new_index: Target position.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if fx_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "fx_index must be >= 0")
        if new_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "new_index must be >= 0")
        return await client.execute("fx_move", track_index=track_index, fx_index=fx_index, new_index=new_index)

    @mcp.tool()
    async def fx_rename(track_index: int, fx_index: int, new_name: str) -> dict:
        """Rename an FX instance's display label (cosmetic — plugin unchanged).

        Use to tag FX you've added yourself so later cleanup can find them
        without affecting other FX on the track. The mix engine uses this
        internally to prefix all its additions with "[MIX] ".

        Args:
            track_index: 0-based track index.
            fx_index: FX slot within the chain.
            new_name: New display name. Max 1000 characters.

        Requires REAPER 6.37+ (for TrackFX_SetNamedConfigParm with
        "renamed_name"). Older REAPER versions will error out cleanly.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if fx_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "fx_index must be >= 0")
        if not new_name:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "new_name must be non-empty")
        if len(new_name) > 1000:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "new_name must be <= 1000 chars")
        return await client.execute(
            "fx_rename",
            track_index=track_index, fx_index=fx_index, new_name=new_name,
        )
