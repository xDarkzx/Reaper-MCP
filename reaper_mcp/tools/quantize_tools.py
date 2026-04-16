"""MIDI quantize + humanize tools."""

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def midi_quantize(
        item_index: int,
        grid_seconds: float,
        strength: float = 1.0,
    ) -> dict:
        """Quantize notes in a MIDI item to a time grid.

        Grid math: for 120 BPM, a 16th note = 0.125s, 8th = 0.25s, quarter = 0.5s.
        At tempo T: grid_sec = (60 / T) * (4 / divisor). For 140 BPM 16ths:
        (60/140) * (4/16) = 0.107s.

        Args:
            item_index: Global item index of the MIDI item.
            grid_seconds: Grid spacing in seconds (see above).
            strength: 0.0 (no quantize) to 1.0 (hard snap). 0.5 = pull halfway.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if grid_seconds <= 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "grid_seconds must be > 0")
        if not 0 <= strength <= 1:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "strength must be 0.0-1.0")
        return await client.execute(
            "midi_quantize",
            item_index=item_index, grid_seconds=grid_seconds, strength=strength,
        )

    @mcp.tool()
    async def midi_humanize(
        item_index: int,
        timing_ms: float = 15.0,
        velocity_amount: int = 8,
    ) -> dict:
        """Add random timing + velocity jitter to all notes in a MIDI item.

        Makes programmed MIDI feel less mechanical. Typical values:
          - Strings / pads: timing_ms=20, velocity=10 (subtle)
          - Drums: timing_ms=8, velocity=15 (tighter timing, wider dynamics)
          - Piano: timing_ms=12, velocity=12

        Args:
            item_index: Global item index of the MIDI item.
            timing_ms: Max random shift in milliseconds (each note ±timing_ms). 0 = off.
            velocity_amount: Max random velocity offset (each note ±amount). 0 = off.
        """
        if item_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "item_index must be >= 0")
        if timing_ms < 0 or timing_ms > 500:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "timing_ms must be 0-500")
        if velocity_amount < 0 or velocity_amount > 64:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "velocity_amount must be 0-64")
        return await client.execute(
            "midi_humanize",
            item_index=item_index, timing_ms=timing_ms, velocity_amount=velocity_amount,
        )

    @mcp.tool()
    async def project_set_ripple_mode(mode: int) -> dict:
        """Set REAPER's ripple edit mode.

        In ripple mode, editing one item shifts everything after it (per-track
        or across all tracks). Critical for dialogue/podcast editing.

        Args:
            mode: 0=off, 1=per-track ripple, 2=all-tracks ripple.
        """
        if mode not in (0, 1, 2):
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE,
                "mode must be 0 (off), 1 (per-track), or 2 (all tracks)",
            )
        return await client.execute("project_set_ripple_mode", mode=mode)
