"""Automation envelope tools — read/write track volume/pan/mute + FX param envelopes."""

import json
import logging

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode

logger = logging.getLogger(__name__)

# Valid named track envelopes (case-sensitive, must match REAPER's label)
_TRACK_ENVELOPE_NAMES = {
    "Volume", "Pan", "Mute", "Width",
    "Volume (Pre-FX)", "Pan (Pre-FX)", "Width (Pre-FX)",
}


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def envelope_get_points(
        track_index: int,
        envelope_name: str = "Volume",
        fx_index: int = -1,
        param_index: int = -1,
        max_results: int = 2000,
    ) -> dict:
        """Read automation points from a track or FX parameter envelope.

        Track envelopes: "Volume", "Pan", "Mute", "Width", "Volume (Pre-FX)",
        "Pan (Pre-FX)", "Width (Pre-FX)".

        For FX param envelopes: pass `fx_index` and `param_index` (get these
        from `fx_get_params`). `envelope_name` is ignored when FX param is set.

        Args:
            track_index: Track.
            envelope_name: Named track envelope (ignored if fx_index+param_index set).
            fx_index: FX slot index, -1 to target track envelope instead.
            param_index: FX parameter index, -1 to target track envelope instead.
            max_results: Cap on returned points (default 2000, prevents context blow-up).
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if max_results <= 0 or max_results > 20000:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "max_results must be 1-20000")
        if fx_index < 0 and envelope_name not in _TRACK_ENVELOPE_NAMES:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"envelope_name must be one of {sorted(_TRACK_ENVELOPE_NAMES)}",
            )
        params = {"track_index": track_index, "envelope_name": envelope_name,
                  "max_results": max_results}
        if fx_index >= 0 and param_index >= 0:
            params["fx_index"] = fx_index
            params["param_index"] = param_index
        return await client.execute("envelope_get_points", **params)

    @mcp.tool()
    async def envelope_add_points(
        track_index: int,
        points: str,
        envelope_name: str = "Volume",
        fx_index: int = -1,
        param_index: int = -1,
        create: bool = True,
    ) -> dict:
        """Batch-insert automation points into an envelope.

        Point shape codes: 0=linear, 1=square, 2=slow start/end, 3=fast start,
        4=fast end, 5=bezier. Tension -1 to +1 for curve skew.

        Value units:
          - Volume track env: linear gain where 1.0 = unity (0 dB), 2.0 ≈ +6 dB,
                              0.5 ≈ -6 dB. Use 10**(db/20) to convert from dB.
          - Pan: -1.0 (hard left) to +1.0 (hard right).
          - Mute: 0.0 or 1.0.
          - FX params: 0.0-1.0 normalized (same as fx_set_param).

        Args:
            track_index: Track.
            points: JSON array of `{"time":s, "value":v, "shape":0, "tension":0}`.
            envelope_name: Track envelope name (ignored with FX param).
            fx_index / param_index: Target FX param envelope (-1 for track env).
            create: If the envelope doesn't exist yet, create it (default True).
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        try:
            pts = json.loads(points)
        except (json.JSONDecodeError, TypeError) as e:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, f"points must be JSON array: {e}")
        if not isinstance(pts, list) or not pts:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "points must be non-empty array")
        if len(pts) > 50000:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE,
                                 f"too many points: {len(pts)} (max 50000 per call)")
        for i, pt in enumerate(pts):
            if not isinstance(pt, dict) or "time" not in pt or "value" not in pt:
                raise ReaperMCPError(
                    ErrorCode.INVALID_PARAMETER,
                    f"point[{i}] must be object with 'time' and 'value' keys",
                )
        payload = {
            "track_index": track_index,
            "envelope_name": envelope_name,
            "points": points,  # pass through as JSON string — Lua will decode
            "create": create,
        }
        if fx_index >= 0 and param_index >= 0:
            payload["fx_index"] = fx_index
            payload["param_index"] = param_index
        return await client.execute("envelope_add_points", **payload)

    @mcp.tool()
    async def envelope_clear_range(
        track_index: int,
        start_time: float,
        end_time: float,
        envelope_name: str = "Volume",
        fx_index: int = -1,
        param_index: int = -1,
    ) -> dict:
        """Delete all envelope points in a time range.

        Args:
            track_index: Track.
            start_time: Range start in seconds (>= 0).
            end_time: Range end in seconds (> start_time).
            envelope_name: Track envelope name.
            fx_index / param_index: Target FX param envelope (-1 for track env).
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")
        if start_time < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "start_time must be >= 0")
        if end_time <= start_time:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE,
                                 "end_time must be > start_time")
        payload = {
            "track_index": track_index,
            "envelope_name": envelope_name,
            "start_time": start_time,
            "end_time": end_time,
        }
        if fx_index >= 0 and param_index >= 0:
            payload["fx_index"] = fx_index
            payload["param_index"] = param_index
        return await client.execute("envelope_clear_range", **payload)
