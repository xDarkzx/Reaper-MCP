"""Mix engine — per-style automated mix pipeline.

Two paths:
  - v2 catalog (25 styles in `catalog/`) — resolves live track NAMES to roles via
    aliases and applies per-role EQ/comp/sends/sidechain from the style profile.
    Covers EDM, Rock, Pop, and adjacent electronic genres.
  - Legacy orchestral path — matches track VSTi names against the old
    `profiles.py` dicts for film-score instruments. Used as fallback when
    the style isn't in the v2 catalog.

Auto-detects FabFilter Pro-Q 3 / Pro-C 2 / Pro-R; falls back to REAPER stock
(ReaEQ / ReaComp / ReaVerbate).
"""

import json
import logging

from reaper_mcp.mix_engine.detect import detect_plugins, PluginSuite
from reaper_mcp.mix_engine.plugins import get_plugin_profile
from reaper_mcp.mix_engine.profiles import (
    VOLUME_STAGING, EQ_PROFILES, COMPRESSION_PROFILES, REVERB_BUSES,
    INSTRUMENT_FAMILIES, SEND_ROUTING,
)

logger = logging.getLogger(__name__)

# Names used to identify mix-engine-created tracks/FX for cleanup
_REVERB_BUS_PREFIX = "MIX:"
_MIX_EQ_NAMES = {"ReaEQ", "FabFilter Pro-Q 3"}
_MIX_COMPRESSOR_NAMES = {"ReaComp", "FabFilter Pro-C 2"}
_MIX_REVERB_NAMES = {"ReaVerbate", "FabFilter Pro-R"}


async def run_mix_pipeline(
    client,
    track_map: dict,
    style: str = "",
    clean: bool = True,
) -> dict:
    """Run the full mix pipeline.

    Dispatches to v2 catalog path if `style` is registered there, else falls
    back to the legacy orchestral path.

    Args:
        client: ReaperClient for IPC.
        track_map: {str(track_index): instrument_name} from live REAPER tracks.
                   Used only by the legacy path.
        style: Style name. If in v2 catalog → v2 path. Empty or orchestral → legacy.
        clean: Remove existing mix FX before applying.

    Returns:
        Summary dict: {success, path, plugin_suite, ...per-path counts...}.
    """
    # Load the v2 catalog on first call
    import reaper_mcp.mix_engine.catalog  # noqa: F401 — populates STYLE_PROFILES
    from reaper_mcp.mix_engine.profiles_v2 import get_profile as get_v2_profile

    v2_profile = get_v2_profile(style) if style else None

    suite = await detect_plugins(client)
    plugin_profile = get_plugin_profile(suite)
    logger.info("Mix engine using plugin suite: %s", suite.value)

    if v2_profile is not None:
        logger.info("Mix path: v2 catalog (%s / family=%s)", v2_profile.name, v2_profile.family)
        return await _run_v2_pipeline(client, v2_profile, plugin_profile, suite, clean)

    logger.info("Mix path: legacy orchestral (style=%r)", style)
    return await _run_legacy_pipeline(client, track_map, plugin_profile, suite, clean)


# ════════════════════════════════════════════════════════════════════
#  v2 PATH — catalog-driven, role-based, sidechain-aware
# ════════════════════════════════════════════════════════════════════

async def _run_v2_pipeline(client, profile, plugin_profile, suite, clean):
    from reaper_mcp.mix_engine.profiles_v2 import resolve_roles

    # 1. Get live tracks with names
    live = await client.execute("track_get_all")
    live_data = live.get("data", live)
    live_tracks = live_data.get("tracks", [])
    if not live_tracks:
        return {"success": False, "error": "No tracks in REAPER project"}

    # 2. Resolve tracks to roles via the style's aliases.
    #    resolve_roles wants [{"index": int, "name": str}]; track_get_all already returns that shape.
    role_map = resolve_roles(profile, live_tracks)  # {track_idx: role_name}
    if not role_map:
        return {
            "success": False,
            "error": f"No track names matched any role in style '{profile.name}'. "
                     f"Rename tracks to include role keywords (kick, snare, sub, pad, lead, vocal, etc).",
            "available_roles": sorted(profile.instrument_roles.keys()),
        }

    # 3. Clean existing mix FX
    if clean:
        await _clean_mix_fx_generic(client, list(role_map.keys()))

    # 4. Apply per-role volume, EQ, compression
    vol_count = await _v2_apply_volume(client, profile, role_map)
    eq_count = await _v2_apply_eq(client, profile, role_map, plugin_profile)
    comp_count = await _v2_apply_comp(client, profile, role_map, plugin_profile)
    pan_count = await _v2_apply_pan(client, profile, role_map)

    # 5. Create reverb buses per the profile's reverb_buses dict (fall back to defaults)
    bus_indices = await _v2_create_reverb_buses(client, profile, plugin_profile)

    # 6. Route sends from each role's .sends list
    send_count = await _v2_route_sends(client, profile, role_map, bus_indices)

    # 7. Apply sidechain specs via the existing setup_sidechain handler
    sidechains_applied = await _v2_apply_sidechains(client, profile, role_map)

    return {
        "success": True,
        "path": "v2_catalog",
        "style": profile.name,
        "family": profile.family,
        "plugin_suite": suite.value,
        "tracks_matched": len(role_map),
        "role_map": {ti: role for ti, role in sorted(role_map.items())},
        "volume_staged": vol_count,
        "pan_applied": pan_count,
        "eq_applied": eq_count,
        "compression_applied": comp_count,
        "reverb_buses": list(bus_indices.keys()),
        "sends_created": send_count,
        "sidechains_applied": sidechains_applied,
    }


async def _v2_apply_volume(client, profile, role_map) -> int:
    tracks_config = []
    for ti, role_name in role_map.items():
        role = profile.instrument_roles.get(role_name)
        if role is None:
            continue
        tracks_config.append({"track_index": ti, "volume_db": role.volume_db})
    if tracks_config:
        await client.execute("configure_tracks", tracks=json.dumps(tracks_config))
    return len(tracks_config)


async def _v2_apply_pan(client, profile, role_map) -> int:
    tracks_config = []
    for ti, role_name in role_map.items():
        role = profile.instrument_roles.get(role_name)
        if role is None or role.pan == 0.0:
            continue
        tracks_config.append({"track_index": ti, "pan": role.pan})
    if tracks_config:
        await client.execute("configure_tracks", tracks=json.dumps(tracks_config))
    return len(tracks_config)


async def _v2_apply_eq(client, profile, role_map, plugin_profile) -> int:
    tracks_with_eq = []
    for ti, role_name in role_map.items():
        role = profile.instrument_roles.get(role_name)
        if role is None or role.eq is None:
            continue
        fx_entry = plugin_profile.eq_fx_chain_entry(role.eq.to_legacy_dict())
        tracks_with_eq.append({"track_index": ti, "fx_chain": [fx_entry]})
    if tracks_with_eq:
        await client.execute("setup_fx_chain", tracks=json.dumps(tracks_with_eq))
    return len(tracks_with_eq)


async def _v2_apply_comp(client, profile, role_map, plugin_profile) -> int:
    tracks_with_comp = []
    for ti, role_name in role_map.items():
        role = profile.instrument_roles.get(role_name)
        if role is None or role.comp is None:
            continue
        fx_entry = plugin_profile.compression_fx_chain_entry(role.comp.to_dict())
        tracks_with_comp.append({"track_index": ti, "fx_chain": [fx_entry]})
    if tracks_with_comp:
        await client.execute("setup_fx_chain", tracks=json.dumps(tracks_with_comp))
    return len(tracks_with_comp)


async def _v2_create_reverb_buses(client, profile, plugin_profile) -> dict:
    """Create reverb buses per the style's `reverb_buses`, or defaults."""
    from reaper_mcp.mix_engine.profiles_v2 import DEFAULT_REVERB_BUSES
    buses = profile.reverb_buses or DEFAULT_REVERB_BUSES

    bus_indices: dict[str, int] = {}
    for bus_name, reverb_bus in buses.items():
        display_name = f"{_REVERB_BUS_PREFIX} {bus_name.title()}"
        config_dict = reverb_bus.to_dict()
        fx_entry = plugin_profile.reverb_fx_chain_entry(config_dict)

        result = await client.execute(
            "setup_effect_bus",
            bus_name=display_name,
            fx_chain=json.dumps([fx_entry]),
            sends_from=json.dumps([]),
            bus_volume_db=0.0,
            bus_color=json.dumps(list(reverb_bus.color)),
        )
        data = result.get("data", result)
        bus_track_idx = data.get("bus_track_index")
        if bus_track_idx is not None:
            bus_indices[bus_name] = bus_track_idx
        else:
            logger.warning("Could not get bus index for v2 bus '%s'", bus_name)
    return bus_indices


async def _v2_route_sends(client, profile, role_map, bus_indices) -> int:
    sends = []
    missing_buses = set()
    for ti, role_name in role_map.items():
        role = profile.instrument_roles.get(role_name)
        if role is None:
            continue
        for rvsend in role.sends:
            bus_ti = bus_indices.get(rvsend.bus)
            if bus_ti is None:
                missing_buses.add((role_name, rvsend.bus))
                continue
            sends.append({
                "source_track": ti,
                "dest_track": bus_ti,
                "volume_db": rvsend.send_db,
            })
    for role_name, bus_name in missing_buses:
        logger.warning(
            "Style profile references reverb bus '%s' for role '%s', but no such bus "
            "was created — send skipped. Check profile.reverb_buses.",
            bus_name, role_name,
        )
    if sends:
        await client.execute("setup_routing", sends=json.dumps(sends))
    return len(sends)


async def _v2_apply_sidechains(client, profile, role_map) -> int:
    """For each SidechainSpec in the profile, find source+target tracks by role
    and invoke setup_sidechain.

    If a role resolves to multiple live tracks, we use the FIRST source track
    as the trigger (one sidechain source avoids pumping chaos) but apply the
    duck to EVERY matched target track (so all pads/bass tracks duck uniformly).

    Specs that reference roles not present in the live project are logged and
    skipped — so the user can see in the result which sidechains didn't wire up.
    """
    if not profile.sidechain:
        return 0

    role_to_tracks: dict[str, list[int]] = {}
    for ti, role in role_map.items():
        role_to_tracks.setdefault(role, []).append(ti)

    applied = 0
    for spec in profile.sidechain:
        src_list = role_to_tracks.get(spec.source, [])
        tgt_list = role_to_tracks.get(spec.target, [])
        if not src_list:
            logger.info(
                "Sidechain %s→%s skipped: source role '%s' not found on any live track",
                spec.source, spec.target, spec.source,
            )
            continue
        if not tgt_list:
            logger.info(
                "Sidechain %s→%s skipped: target role '%s' not found on any live track",
                spec.source, spec.target, spec.target,
            )
            continue

        src_ti = src_list[0]
        for tgt_ti in tgt_list:
            if src_ti == tgt_ti:
                continue
            try:
                await client.execute(
                    "setup_sidechain",
                    source_track=src_ti,
                    target_track=tgt_ti,
                    amount=spec.amount,
                    attack_ms=spec.attack_ms,
                    release_ms=spec.release_ms,
                )
                applied += 1
            except Exception as e:
                logger.warning(
                    "Sidechain %s→%s on tracks %d→%d failed: %s",
                    spec.source, spec.target, src_ti, tgt_ti, e,
                )
    return applied


# ════════════════════════════════════════════════════════════════════
#  LEGACY PATH — dict-based, orchestral, unchanged behavior
# ════════════════════════════════════════════════════════════════════

async def _run_legacy_pipeline(client, track_map, plugin_profile, suite, clean):
    if clean:
        await _clean_mix_fx(client, track_map, plugin_profile)

    vol_applied = await _apply_volume_staging(client, track_map)
    eq_applied = await _apply_eq(client, track_map, plugin_profile)
    comp_applied = await _apply_compression(client, track_map, plugin_profile)
    bus_indices = await _create_reverb_buses(client, plugin_profile)
    sends_created = await _route_sends(client, track_map, bus_indices)

    return {
        "success": True,
        "path": "legacy_orchestral",
        "plugin_suite": suite.value,
        "volume_staged": vol_applied,
        "eq_applied": eq_applied,
        "compression_applied": comp_applied,
        "reverb_buses": list(bus_indices.keys()),
        "sends_created": sends_created,
    }


async def _clean_mix_fx_generic(client, track_indices: list[int]) -> None:
    """Remove previously-added mix EQ/compressor from the given tracks and
    delete MIX:* reverb buses.

    ⚠ LIMITATION: This function removes every ReaEQ / ReaComp / Pro-Q 3 /
    Pro-C 2 instance on the given tracks — including any the user added
    manually, since the mix engine doesn't yet mark its own FX with a
    distinguishing prefix. Operation is scoped to tracks in `track_indices`
    (only tracks the mix engine is currently processing), so user FX on
    other tracks is never touched.

    Callers that don't want this behaviour should pass `clean=False` to
    `engine_mix` / `engine_master`. Future: add an fx_rename handler and
    tag mix-engine FX with a "[MIX]" prefix.
    """
    removed = 0
    for ti in track_indices:
        try:
            chain_result = await client.execute("fx_get_chain", track_index=ti)
            data = chain_result.get("data", chain_result)
            fx_chain = data.get("fx_chain", [])
            for fx in reversed(fx_chain):
                fx_name = fx.get("name", "")
                for mix_fx_name in _MIX_EQ_NAMES | _MIX_COMPRESSOR_NAMES:
                    if mix_fx_name in fx_name:
                        await client.execute(
                            "fx_remove", track_index=ti, fx_index=fx["index"]
                        )
                        logger.info("Cleanup: removed %r from track %d", fx_name, ti)
                        removed += 1
                        break
        except Exception as e:
            logger.warning("Could not clean FX on track %d: %s", ti, e)

    buses_removed = 0
    try:
        all_tracks = await client.execute("track_get_all")
        data = all_tracks.get("data", all_tracks)
        tracks = data.get("tracks", [])
        for t in reversed(tracks):
            name = t.get("name", "")
            if name.startswith(_REVERB_BUS_PREFIX):
                await client.execute("track_delete", track_index=t["index"])
                buses_removed += 1
    except Exception as e:
        logger.warning("Could not clean reverb buses: %s", e)

    if removed or buses_removed:
        logger.info("Cleanup summary: %d FX removed, %d reverb buses deleted.", removed, buses_removed)


async def _clean_mix_fx(client, track_map: dict, plugin_profile) -> None:
    await _clean_mix_fx_generic(client, [int(k) for k in track_map.keys()])


async def _apply_volume_staging(client, track_map: dict) -> int:
    tracks_config = []
    for ti_str, inst_name in track_map.items():
        vol_db = VOLUME_STAGING.get(inst_name)
        if vol_db is not None:
            tracks_config.append({"track_index": int(ti_str), "volume_db": vol_db})
    if tracks_config:
        await client.execute("configure_tracks", tracks=json.dumps(tracks_config))
    return len(tracks_config)


async def _apply_eq(client, track_map: dict, plugin_profile) -> int:
    tracks_with_eq = []
    for ti_str, inst_name in track_map.items():
        eq_profile = EQ_PROFILES.get(inst_name)
        if not eq_profile:
            continue
        fx_entry = plugin_profile.eq_fx_chain_entry(eq_profile)
        tracks_with_eq.append({"track_index": int(ti_str), "fx_chain": [fx_entry]})
    if tracks_with_eq:
        await client.execute("setup_fx_chain", tracks=json.dumps(tracks_with_eq))
    return len(tracks_with_eq)


async def _apply_compression(client, track_map: dict, plugin_profile) -> int:
    tracks_with_comp = []
    for ti_str, inst_name in track_map.items():
        comp_profile = COMPRESSION_PROFILES.get(inst_name)
        if not comp_profile:
            continue
        fx_entry = plugin_profile.compression_fx_chain_entry(comp_profile)
        tracks_with_comp.append({"track_index": int(ti_str), "fx_chain": [fx_entry]})
    if tracks_with_comp:
        await client.execute("setup_fx_chain", tracks=json.dumps(tracks_with_comp))
    return len(tracks_with_comp)


async def _create_reverb_buses(client, plugin_profile) -> dict:
    bus_indices = {}
    for bus_name, config in REVERB_BUSES.items():
        display_name = f"{_REVERB_BUS_PREFIX} {bus_name.title()}"
        color = config.get("color", [128, 128, 128])
        fx_entry = plugin_profile.reverb_fx_chain_entry(config)
        result = await client.execute(
            "setup_effect_bus",
            bus_name=display_name,
            fx_chain=json.dumps([fx_entry]),
            sends_from=json.dumps([]),
            bus_volume_db=0.0,
            bus_color=json.dumps(color),
        )
        data = result.get("data", result)
        bus_track_idx = data.get("bus_track_index")
        if bus_track_idx is not None:
            bus_indices[bus_name] = bus_track_idx
        else:
            logger.warning("Could not get bus index for '%s'", bus_name)
    return bus_indices


async def _route_sends(client, track_map: dict, bus_indices: dict) -> int:
    sends = []
    for ti_str, inst_name in track_map.items():
        family = INSTRUMENT_FAMILIES.get(inst_name)
        if not family:
            continue
        ti = int(ti_str)
        for bus_name, bus_ti in bus_indices.items():
            routing = SEND_ROUTING.get(bus_name, {})
            send_db = routing.get(family)
            if send_db is not None:
                sends.append({"source_track": ti, "dest_track": bus_ti, "volume_db": send_db})
    if sends:
        await client.execute("setup_routing", sends=json.dumps(sends))
    return len(sends)
