"""Mix tools — one-click automated mix + master pipeline MCP tools."""

import logging

from mcp.server.fastmcp import FastMCP
from reaper_mcp.tools.compose_helpers import _build_live_track_map
from reaper_mcp.safety import ensure_backup

logger = logging.getLogger(__name__)


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def engine_fix_mix(style: str = "", include_master: bool = True) -> dict:
        """Rescue a muddy / harsh / unbalanced mix with a single call.

        Applies corrective EQ per track based on what the track sounds like
        (bass / vocal / lead / drum / other), classified by name (and by role
        if `style` is a known v2 catalog style).

        Each track gets:
          - HP filter at 80-120 Hz (except bass-family, which keeps low end)
          - Narrow cut at 250 Hz (tames low-mid mud)
          - Narrow cut at 3 kHz for vocals/leads (tames harshness)
          - High-shelf air boost at 12 kHz for vocals/leads/perc

        Plus optional master chain: bus glue comp + brick-wall limiter at -1 dB.

        Call this when a mix sounds "stuffy" or "harsh" and you want a quick
        corrective pass before fine-tuning. Doesn't replace `engine_mix` — use
        this to fix something already mixed (poorly) by someone else.

        Args:
            style: Optional v2 catalog style (e.g. melodic_dubstep) for better
                   track classification via aliases. Empty = keyword fallback.
            include_master: Also apply the emergency master chain (default True).
        """
        from reaper_mcp.mix_engine.fix_mix import run_fix_mix
        return await run_fix_mix(client, style, include_master)

    @mcp.tool()
    async def engine_master(style: str, clean: bool = True) -> dict:
        """Apply a professional mastering chain to the master bus for the given style.

        Chain applied (in order): HP 25Hz → bus glue comp → tonal shelf EQ →
        stereo width → brick-wall limiter. Targets per-style LUFS and true-peak ceiling.

        Auto-detects FabFilter Pro-L 2 / Pro-C 2 / Pro-Q 3; falls back to REAPER stock
        (ReaLimit / ReaComp / ReaEQ).

        Supported styles: melodic_dubstep, big_room, future_bass, future_house, deep_house,
        tech_house, progressive_house, dubstep, trap, drum_and_bass, trance, modern_pop,
        dance_pop, indie_pop, rnb_pop, alt_rock, classic_rock, pop_rock, hard_rock, punk,
        post_rock, synthwave, lofi, ambient, hiphop, swing_jazz, jazz_fusion, latin_jazz,
        classical_chamber, cinematic_trailer, ambient_orchestral, classic_funk, motown_soul,
        neo_soul, disco_funk (35 total). Any other name falls through to the legacy
        per-instrument orchestral master chain.

        Args:
            style: Style name from the catalog (required).
            clean: Remove previously added master FX before applying (default True).
        """
        backup = await ensure_backup(client) if clean else None
        # Ensure catalog is loaded
        import reaper_mcp.mix_engine.catalog  # noqa: F401
        from reaper_mcp.mix_engine.master import run_master_pipeline

        result = await run_master_pipeline(client, style, clean)
        if isinstance(result, dict) and backup:
            result["backup"] = backup
        return result

    @mcp.tool()
    async def engine_mix(style: str = "", clean: bool = True) -> dict:
        """One-click professional mix pipeline. Applies volume staging, pan, EQ, compression, reverb buses, and sidechain.

        Two paths depending on the style:
          - **v2 catalog** (EDM / Rock / Pop / Electronic / Jazz / Orchestral /
            Funk-Soul — 35 styles): resolves live track NAMES to instrument
            roles via alias matching (e.g. a track named "Kick" → role "kick").
            Applies per-role EQ/comp/sends and profile-defined sidechain
            relationships. Rename your tracks to include role keywords like
            "kick", "snare", "sub", "pad", "lead", "vocal" — or for the
            orchestral v2 styles, consolidated section names like "strings",
            "brass", "woodwinds", "choir".
          - **Legacy orchestral**: for a full per-instrument multi-mic template
            (separate Violin 1 / Violin 2 / Viola / Cello / individual winds &
            brass tracks) — matches track VSTi names against the BBC/Spitfire
            instrument map with per-instrument-tuned EQ/comp, not just one
            curve per section. Finer-grained than the v2 orchestral styles.
            Triggered by any style name NOT in the v2 catalog (empty string
            works).

        Auto-detects FabFilter (Pro-Q 3, Pro-C 2, Pro-R) or falls back to REAPER
        stock (ReaEQ, ReaComp, ReaVerbate).

        Args:
            style: Style name. For v2: melodic_dubstep, big_room, future_bass, modern_pop,
                   alt_rock, swing_jazz, classical_chamber, classic_funk, etc. (35 total).
                   Empty, or any name not in the v2 catalog, → legacy per-instrument path.
            clean: Remove existing mix FX before applying (default True).
        """
        import reaper_mcp.mix_engine.catalog  # noqa: F401 — register catalog
        from reaper_mcp.mix_engine.profiles_v2 import get_profile as get_v2

        is_v2 = style and get_v2(style) is not None

        # Get track instruments (always — used by legacy path; cheap otherwise)
        ti_result = await client.execute("get_track_instruments")
        data = ti_result.get("data", ti_result)
        tracks_list = data.get("tracks", [])
        if not tracks_list:
            return {"success": False, "error": "No tracks found in REAPER project"}

        track_map = _build_live_track_map(tracks_list)

        # v2 path doesn't need VSTi instrument detection — it matches by track name.
        # Legacy path requires it.
        if not is_v2 and not track_map:
            return {
                "success": False,
                "error": "No recognized orchestral instruments on any track. "
                         "For EDM/rock/pop, pass a v2 style name (e.g. melodic_dubstep) "
                         "and name your tracks with role keywords (kick, snare, pad, etc).",
            }

        backup = await ensure_backup(client) if clean else None
        from reaper_mcp.mix_engine import run_mix_pipeline
        result = await run_mix_pipeline(client, track_map, style, clean)
        if isinstance(result, dict) and backup:
            result["backup"] = backup
        return result
