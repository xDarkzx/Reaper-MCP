"""Sidechain MCP tool — set up kick→bass/pad pumping and ducking."""

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def setup_sidechain(
        source_track: int,
        target_track: int,
        amount: float = 0.7,
        attack_ms: float = 5.0,
        release_ms: float = 180.0,
        ratio: float = 0.0,
        threshold_db: float = 0.0,
        compressor_name: str = "ReaComp",
        fx_index: int = -1,
        send_db: float = 0.0,
    ) -> dict:
        """Set up sidechain compression: source pumps/ducks the target.

        Creates an aux send from source→target on channels 3/4, sets the target
        track to 4 channels, finds-or-adds a compressor on the target, pin-maps
        channels 3/4 to the compressor's sidechain input pins, and configures
        the compressor for pumping character.

        Use cases:
          - EDM kick → bass (classic pumping bassline)
          - EDM kick → pads (breathing pad)
          - Vocal lead → synth pad (pad ducks under vocals)
          - Snare → reverb tail (dynamic reverb)

        Args:
            source_track: Track whose signal drives the ducking (e.g. kick).
            target_track: Track that gets ducked (e.g. pad, bass).
            amount: 0.0 (subtle) to 1.0 (heavy pumping). Defaults to 0.7.
                    Translates to threshold/ratio if those are not explicit.
            attack_ms: Comp attack. Fast (2-10ms) = tight pump. Default 5.
            release_ms: Comp release. 80-250ms for classic EDM pump. Default 180.
            ratio: Compression ratio. 0 = derive from amount. Typical 4:1 to 10:1.
            threshold_db: Threshold in dB. 0 = derive from amount. Typical -15 to -30.
            compressor_name: "ReaComp" (default), "FabFilter Pro-C 2", or any loaded compressor.
            fx_index: Use an existing FX by index on the target. -1 = find-or-add by name.
            send_db: Aux send level in dB (drives how hard the compressor reacts). 0 = unity.

        Returns: {success, send_index, fx_index, compressor_name, threshold_db, ratio, ...}
        """
        if source_track < 0 or target_track < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track indices must be >= 0")
        if source_track == target_track:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "source and target must differ")
        if not 0.0 <= amount <= 1.0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "amount must be 0.0-1.0")
        if attack_ms <= 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "attack_ms must be > 0")
        if release_ms <= 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "release_ms must be > 0")

        payload = {
            "source_track": source_track,
            "target_track": target_track,
            "amount": amount,
            "attack_ms": attack_ms,
            "release_ms": release_ms,
            "compressor_name": compressor_name,
            "send_db": send_db,
        }
        if ratio > 0:
            payload["ratio"] = ratio
        if threshold_db != 0.0:
            payload["threshold_db"] = threshold_db
        if fx_index >= 0:
            payload["fx_index"] = fx_index

        return await client.execute("setup_sidechain", **payload)
