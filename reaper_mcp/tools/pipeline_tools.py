"""Higher-level production pipelines built on existing primitives.

These are composite tools that orchestrate multiple low-level MCP calls
(send_create, setup_effect_bus, setup_fx_chain, etc.) into common
production moves:

  - `setup_parallel_compression` — NY-style "crush" bus blended back in
  - `setup_drum_bus` — dedicated drum group bus with glue comp
  - `setup_vocal_chain` — single-call vocal strip (HP + comp + EQ + plate send)
  - `bounce_stems` — render selected tracks to audio stems
"""

import json
import logging

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode

logger = logging.getLogger(__name__)


def register(mcp: FastMCP):
    from reaper_mcp.main import client
    from reaper_mcp.mix_engine.detect import detect_plugins
    from reaper_mcp.mix_engine.plugins import get_plugin_profile

    @mcp.tool()
    async def setup_parallel_compression(
        source_tracks: str,
        bus_name: str = "BUS: Parallel Comp",
        send_db: float = 0.0,
        return_db: float = -8.0,
        threshold_db: float = -24.0,
        ratio: float = 10.0,
        attack_ms: float = 1.0,
        release_ms: float = 100.0,
    ) -> dict:
        """Create a NY-style parallel compression bus and route source tracks to it.

        Classic use: crush drums or vocals with a heavy compressor on a parallel
        bus, then blend the crushed signal back in subtly with the dry. Adds
        perceived density and power without destroying transients.

        Args:
            source_tracks: JSON array of track indices to send to the parallel bus, e.g. "[0,1,2]".
            bus_name: Display name for the created bus track.
            send_db: Send level from each source to the bus (0 = unity).
            return_db: Bus output (return) level. -8 is a typical subtle blend.
            threshold_db: Compressor threshold. -24 to -30 for heavy crush.
            ratio: Compression ratio. 10:1 or higher for that "smashed" sound.
            attack_ms: Fast (1-3 ms) for tight pumping.
            release_ms: Medium (80-120 ms) typical.
        """
        try:
            src_list = json.loads(source_tracks)
        except (json.JSONDecodeError, TypeError) as e:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                 f"source_tracks must be JSON array: {e}")
        if not isinstance(src_list, list) or not src_list:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                 "source_tracks must be a non-empty array")

        suite = await detect_plugins(client)
        plugin_profile = get_plugin_profile(suite)

        # Build compressor FX entry with heavy-parallel character
        comp_profile = {
            "threshold_db": threshold_db, "ratio": ratio,
            "attack_ms": attack_ms, "release_ms": release_ms,
            "makeup_db": 4.0, "knee_db": 2.0,
        }
        comp_fx = plugin_profile.compression_fx_chain_entry(comp_profile)

        # Build sends_from array
        sends_from = [{"source_track": int(ti), "volume_db": send_db} for ti in src_list]

        result = await client.execute(
            "setup_effect_bus",
            bus_name=bus_name,
            fx_chain=json.dumps([comp_fx]),
            sends_from=json.dumps(sends_from),
            bus_volume_db=return_db,
            bus_color=json.dumps([210, 80, 80]),
        )
        data = result.get("data", result)
        return {
            "success": True,
            "bus_track_index": data.get("bus_track_index"),
            "bus_name": bus_name,
            "sources_routed": len(src_list),
            "comp": comp_profile,
            "return_db": return_db,
            "plugin_suite": suite.value,
        }

    @mcp.tool()
    async def setup_drum_bus(
        source_tracks: str,
        bus_name: str = "BUS: Drums",
        return_db: float = 0.0,
        glue_threshold_db: float = -12.0,
        glue_ratio: float = 2.0,
    ) -> dict:
        """Group drum tracks into a dedicated bus with a glue compressor.

        This is a lighter-touch version of parallel compression — the bus is a
        full sub-mix of the drums, with gentle comp gluing them together rather
        than crushing them. Use this to control the drum group's overall level
        and apply shared processing (additional EQ, saturation) above it.

        Args:
            source_tracks: JSON array of drum track indices, e.g. "[0,1,2,3]".
            bus_name: Display name for the drum bus.
            return_db: Bus output level (0 = unity, no change vs pre-bus).
            glue_threshold_db: Glue comp threshold (-10 to -14 typical).
            glue_ratio: Glue comp ratio (1.5-2.5 for gentle glue).
        """
        try:
            src_list = json.loads(source_tracks)
        except (json.JSONDecodeError, TypeError) as e:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                 f"source_tracks must be JSON array: {e}")
        if not isinstance(src_list, list) or not src_list:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                 "source_tracks must be a non-empty array")

        suite = await detect_plugins(client)
        plugin_profile = get_plugin_profile(suite)

        comp_profile = {
            "threshold_db": glue_threshold_db, "ratio": glue_ratio,
            "attack_ms": 15.0, "release_ms": 100.0,
            "makeup_db": 2.0, "knee_db": 6.0,
        }
        comp_fx = plugin_profile.compression_fx_chain_entry(comp_profile)

        sends_from = [{"source_track": int(ti), "volume_db": 0.0} for ti in src_list]

        result = await client.execute(
            "setup_effect_bus",
            bus_name=bus_name,
            fx_chain=json.dumps([comp_fx]),
            sends_from=json.dumps(sends_from),
            bus_volume_db=return_db,
            bus_color=json.dumps([200, 130, 60]),
        )
        data = result.get("data", result)
        return {
            "success": True,
            "bus_track_index": data.get("bus_track_index"),
            "bus_name": bus_name,
            "sources_routed": len(src_list),
            "glue_comp": comp_profile,
            "plugin_suite": suite.value,
        }

    @mcp.tool()
    async def setup_vocal_chain(
        track_index: int,
        hp_freq: float = 100.0,
        comp_threshold_db: float = -16.0,
        comp_ratio: float = 3.0,
        air_boost_db: float = 1.5,
        mud_cut_db: float = -2.0,
        harsh_cut_db: float = -1.5,
        plate_bus_name: str = "BUS: Vocal Plate",
        plate_send_db: float = -8.0,
    ) -> dict:
        """One-call vocal-chain setup: HP + compressor + tonal EQ + plate reverb send.

        Creates (or reuses) a dedicated plate reverb bus and sends the vocal
        track to it. Designed to give a polished broadcast-ready vocal with one call.

        Chain applied in order on the vocal track:
          1. HP filter at `hp_freq`
          2. Mud cut: -2dB at 250Hz, Q=1.8
          3. Presence boost: +1.5dB at 4kHz, Q=1.2
          4. Harsh cut: -1.5dB at 3kHz, Q=3 (de-harsh)
          5. Air lift: +1.5dB high-shelf at 12kHz
          6. Compressor (3:1, -16dB threshold, vocal character)
        Plus a send to a plate reverb bus at `plate_send_db`.

        Args:
            track_index: Track to process.
            hp_freq: High-pass cutoff in Hz.
            comp_threshold_db / comp_ratio: Compression settings.
            air_boost_db / mud_cut_db / harsh_cut_db: EQ amounts in dB.
            plate_bus_name: Bus track name (reused if exists).
            plate_send_db: Send level from vocal to the plate bus.
        """
        if track_index < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0")

        suite = await detect_plugins(client)
        plugin_profile = get_plugin_profile(suite)

        # EQ entry
        eq_profile = {
            "hp_freq": hp_freq,
            "cuts": [
                {"freq": 250, "gain_db": mud_cut_db, "q": 1.8},
                {"freq": 3000, "gain_db": harsh_cut_db, "q": 3.0},
            ],
            "boosts": [
                {"freq": 4000, "gain_db": 1.5, "q": 1.2},
                {"freq": 12000, "gain_db": air_boost_db, "q": 0.8, "shape": "high_shelf"},
            ],
        }
        eq_fx = plugin_profile.eq_fx_chain_entry(eq_profile)

        # Compressor entry
        comp_profile = {
            "threshold_db": comp_threshold_db, "ratio": comp_ratio,
            "attack_ms": 8.0, "release_ms": 100.0,
            "makeup_db": 2.5, "knee_db": 4.0,
        }
        comp_fx = plugin_profile.compression_fx_chain_entry(comp_profile)

        # Apply EQ + compressor in order
        await client.execute(
            "setup_fx_chain",
            tracks=json.dumps([{
                "track_index": track_index,
                "fx_chain": [eq_fx, comp_fx],
            }]),
        )

        # Look for an existing plate bus (reuse if exists)
        all_tracks_raw = await client.execute("track_get_all")
        all_data = all_tracks_raw.get("data", all_tracks_raw)
        existing = all_data.get("tracks", [])
        plate_idx = None
        target_name_lower = plate_bus_name.lower()
        for t in existing:
            if (t.get("name") or "").lower() == target_name_lower:
                plate_idx = t.get("index")
                break

        if plate_idx is None:
            # Create a new plate reverb bus
            reverb_config = {
                "room_size": 0.55, "dampening": 0.20, "wet_db": -6.0,
                "lowpass_hz": 16000, "hipass_hz": 250, "width": 1.1,
            }
            reverb_fx = plugin_profile.reverb_fx_chain_entry(reverb_config)
            bus_result = await client.execute(
                "setup_effect_bus",
                bus_name=plate_bus_name,
                fx_chain=json.dumps([reverb_fx]),
                sends_from=json.dumps([{"source_track": track_index, "volume_db": plate_send_db}]),
                bus_volume_db=0.0,
                bus_color=json.dumps([160, 70, 180]),
            )
            bus_data = bus_result.get("data", bus_result)
            plate_idx = bus_data.get("bus_track_index")
        else:
            # Reuse — add a send from this vocal to the existing plate bus
            await client.execute(
                "setup_routing",
                sends=json.dumps([{
                    "source_track": track_index,
                    "dest_track": plate_idx,
                    "volume_db": plate_send_db,
                }]),
            )

        return {
            "success": True,
            "track_index": track_index,
            "plate_bus_index": plate_idx,
            "plate_bus_name": plate_bus_name,
            "plugin_suite": suite.value,
        }

    @mcp.tool()
    async def bounce_stems(
        track_indices: str,
        output_dir: str = "",
        format: str = "wav",
    ) -> dict:
        """Render the given tracks as individual audio stems (in-project).

        Selects the tracks, then invokes REAPER's "Render tracks to stereo stem
        tracks" action (command ID 40892). Resulting stems are added to the
        project as new tracks.

        **IMPORTANT SIDE EFFECTS (undocumented by REAPER, confirmed by behavior):**
          - The source tracks are AUTOMATICALLY MUTED after rendering so you
            can hear the stems instead of double-playback. If you need to
            compare or continue editing the originals, call `track_set_mute(False)`
            on them after this finishes.
          - New stem tracks are inserted below the source tracks.
          - Works with pre-fader + post-FX rendering (standard REAPER behavior).

        Requires REAPER 5.x or newer. For export to audio files on disk, use
        `project_export_audio` instead — this tool is for in-project stemming.

        Args:
            track_indices: JSON array of track indices to stem, e.g. "[0,1,2]".
            output_dir: Reserved (not currently used — in-project stemming).
            format: Reserved (not currently used).
        """
        try:
            src_list = json.loads(track_indices)
        except (json.JSONDecodeError, TypeError) as e:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                 f"track_indices must be JSON array: {e}")
        if not isinstance(src_list, list) or not src_list:
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER,
                                 "track_indices must be a non-empty array")

        # Deselect all, then additively select each target track
        await client.execute("selection_deselect_all_tracks")
        for ti in src_list:
            # `selected=True` adds to selection (exclusive defaults to False)
            await client.execute("track_select", track_index=int(ti), selected=True)

        # Action 40892 = Track: Render selected tracks to stereo stem tracks (and mute originals)
        result = await client.execute("project_main_action", command_id=40892)
        return {
            "success": True,
            "tracks_stemmed": len(src_list),
            "action_result": result,
        }
