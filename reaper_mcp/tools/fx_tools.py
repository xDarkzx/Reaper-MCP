import json

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode
from reaper_mcp_shared.constants import MAX_PARAMS_PER_BATCH, MAX_SCAN_PARAMS
from reaper_mcp_shared.plugin_cache import infer_curve, load_cached_map, save_cached_map


def validate_batch_params(parsed) -> None:
    """Validates the parsed JSON body of fx_set_params_batch's `params`
    argument, raising ReaperMCPError on the first problem found. Extracted
    as a plain function (not inlined in the tool) so it's directly
    unit-testable without needing to mock the REAPER IPC client at all."""
    if not isinstance(parsed, list) or not parsed:
        raise ReaperMCPError(
            ErrorCode.INVALID_PARAMETER,
            f"`params` must be a non-empty JSON array, got {type(parsed).__name__}",
        )
    if len(parsed) > MAX_PARAMS_PER_BATCH:
        raise ReaperMCPError(
            ErrorCode.VALUE_OUT_OF_RANGE,
            f"Too many items ({len(parsed)}) — split into batches <= {MAX_PARAMS_PER_BATCH}.",
        )
    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"params[{i}] must be an object, got {type(item).__name__}",
            )
        for k in ("track_index", "fx_index", "value"):
            if k not in item:
                raise ReaperMCPError(
                    ErrorCode.INVALID_PARAMETER, f"params[{i}] is missing required key '{k}'"
                )
        has_index = "param_index" in item
        # bool(...) matters here, not just truthiness: `and` returns the
        # operand itself (e.g. a non-empty string), and `has_index ==
        # has_name` below needs a real bool on both sides to correctly
        # detect "both given" or "neither given" - confirmed by a real
        # failing test: `True == "Band 1 Shape"` and `False == ""` are
        # both False in Python, silently letting invalid combinations
        # through the check that was meant to catch them.
        has_name = bool(item.get("param_name"))
        if has_index == has_name:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"params[{i}] must have exactly one of param_index or param_name",
            )
        value = item["value"]
        if not (isinstance(value, (int, float)) and 0.0 <= value <= 1.0):
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE, f"params[{i}].value must be 0.0-1.0, got {value!r}"
            )


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
    async def fx_set_params_batch(params: str) -> dict:
        """Set many FX parameters in one round-trip instead of one call per
        parameter. Setting up a single EQ band properly (Used, Enabled,
        Frequency, Gain, Shape) is 4-5 separate fx_set_param/
        fx_set_param_by_name calls today — a real, reported cost at scale
        (a handful of bands across a few tracks adds up to 40-60 calls).
        This is that same operation, batched: any mix of tracks and FX in
        one call.

        Each item is independent (its own track_index/fx_index/value, plus
        either param_index or param_name) and fails on its own — one bad
        item (typo'd name, wrong track) does not abort the rest of the
        batch, unlike a single JSON-parse failure for the whole `params`
        argument, which does fail everything (nothing could be attempted
        at all in that case).

        Args:
            params: JSON array of objects, each:
                `{"track_index": int, "fx_index": int, "value": float 0.0-1.0,
                "param_index": int}` OR the same with `"param_name": str`
                instead of `param_index` (fuzzy match, same as
                fx_set_param_by_name). Exactly one of param_index/param_name
                per item.

        Returns `{"results": [...], "count": int, "fail_count": int}` — each
        result is `{"success": bool, "item_index": int, ...}`: on success,
        `param_index`, `name`, `value`, `display`; on failure, `error`.
        Check `fail_count` rather than assuming a 200-shaped response means
        every item landed.
        """
        try:
            parsed = json.loads(params)
        except json.JSONDecodeError as e:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"`params` is not valid JSON: {e.msg} (line {e.lineno}, col {e.colno})",
            )
        validate_batch_params(parsed)
        return await client.execute("fx_set_params_batch", params=params)

    @mcp.tool()
    async def fx_scan_params(track_index: int, fx_index: int) -> dict:
        """On-demand fallback: sweep a plugin's parameters to learn their real
        range/units/curve shape, when you're genuinely unsure and about to
        guess. NOT a general "understand this plugin" tool, and not something
        to call routinely or proactively on every plugin you touch.

        Scope: this answers "what range/units does this specific parameter
        actually use" (calibration) — nothing more. It does not explain what
        a parameter *means* or what a plugin is *for*; reasoning about a
        plugin's purpose and a vaguely-named control ("Character," "Drive")
        is something you're already equipped to do from general knowledge,
        the same way you already handle FabFilter without this tool. Reach
        for fx_scan_params only when that reasoning genuinely isn't enough —
        e.g. an obscure/freeware plugin with no clear labeling, or a
        specific parameter whose behavior turned out to be surprising (see
        docs/superpowers/specs/2026-08-06-vst-param-autoscan-design.md for
        the reasoning behind this scope).

        Caches the result by plugin name, so repeat scans of the same plugin
        (even in a different project) return instantly from the on-disk
        cache instead of touching REAPER again. Briefly writes and restores
        every parameter's value during the sweep, and can take longer on
        plugins with many parameters — another reason this is deliberately
        separate from fx_get_params rather than folded into routine reads.

        Args:
            track_index: 0-based track index.
            fx_index: 0-based FX chain index.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if fx_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "fx_index must be >= 0")

        chain = await client.execute("fx_get_chain", track_index=track_index)
        fx_list = chain.get("data", {}).get("fx_chain", [])
        if not 0 <= fx_index < len(fx_list):
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "fx_index out of range for this track")
        plugin_name = fx_list[fx_index]["name"]

        cached = load_cached_map(plugin_name)
        if cached is not None:
            return {**cached, "from_cache": True}

        result = await client.execute_long(
            "fx_scan_params", track_index=track_index, fx_index=fx_index, max_params=MAX_SCAN_PARAMS,
        )
        scan_data = result.get("data", {})
        params = []
        for entry in scan_data.get("params", []):
            step_count = entry.get("step_count")
            curve, unit = infer_curve(entry["samples"], step_count)
            params.append({
                "index": entry["index"],
                "name": entry["name"],
                "samples": entry["samples"],
                "step_count": step_count,
                "inferred_curve": curve,
                "inferred_unit": unit,
            })
        truncated = bool(scan_data.get("truncated", False))
        save_cached_map(plugin_name, params, truncated)
        return {
            "plugin_name": plugin_name,
            "truncated": truncated,
            "params": params,
            "from_cache": False,
        }

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
