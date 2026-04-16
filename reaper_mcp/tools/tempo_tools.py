"""Tempo map tools — add/list/delete tempo and time-signature markers."""

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def tempo_list_markers() -> dict:
        """List all tempo + time-signature markers in the project.

        Returns each marker's time, measure, beat, BPM, and time signature.
        Use this to see the project's tempo map before editing.
        """
        return await client.execute("tempo_list_markers")

    @mcp.tool()
    async def tempo_add_marker(
        position: float,
        bpm: float = 0,
        time_sig_num: int = 0,
        time_sig_denom: int = 0,
        linear: bool = False,
    ) -> dict:
        """Add a tempo and/or time-signature marker at a given time.

        Args:
            position: Time in seconds (>= 0).
            bpm: New BPM at this marker. 0 = inherit from previous.
            time_sig_num: Numerator (e.g. 3 for 3/4). 0 = inherit.
            time_sig_denom: Denominator (e.g. 4 for 3/4). 0 = inherit.
            linear: True = smooth BPM ramp to the NEXT marker; False = instant change.
        """
        if position < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "position must be >= 0")
        if bpm and (bpm < 20 or bpm > 999):
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "bpm must be 20-999 (or 0 to inherit)")
        if time_sig_num < 0 or time_sig_num > 64:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "time_sig_num must be 0-64")
        if time_sig_denom not in (0, 1, 2, 4, 8, 16, 32, 64):
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE,
                "time_sig_denom must be 1/2/4/8/16/32/64 (or 0 to inherit)",
            )
        return await client.execute(
            "tempo_add_marker",
            position=position, bpm=bpm,
            time_sig_num=time_sig_num, time_sig_denom=time_sig_denom,
            linear=linear,
        )

    @mcp.tool()
    async def tempo_delete_marker(index: int) -> dict:
        """Delete a tempo/time-sig marker by its index (from `tempo_list_markers`).

        Args:
            index: 0-based marker index.
        """
        if index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "index must be >= 0")
        return await client.execute("tempo_delete_marker", index=index)

    @mcp.tool()
    async def tempo_clear_all() -> dict:
        """Delete every tempo/time-sig marker — resets the project to its base tempo.

        Does NOT change the base BPM itself; use `transport_set_bpm` for that.
        """
        return await client.execute("tempo_clear_all")
