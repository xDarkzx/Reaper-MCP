"""Fix-mix pipeline — rescue a muddy / harsh / unbalanced mix.

Strategy (per-track, name-driven):
  1. HP filter on every non-bass track at 80 Hz (removes rumble + builds clarity)
  2. Narrow cut at 250 Hz on every track (tames low-mid mud — the #1 EDM problem)
  3. Narrow cut at 3 kHz on vocal/lead roles (tames harshness)
  4. Light high-shelf boost at 12 kHz on vocals/leads/perc (adds air)
  5. Master chain: bus glue comp + limiter at -1 dB ceiling

Designed to make a bad mix noticeably better in a single call. Not a replacement
for a real mix, but a useful starting point or emergency clean-up.
"""

import json
import logging

from reaper_mcp.mix_engine.detect import detect_plugins
from reaper_mcp.mix_engine.plugins import get_plugin_profile

logger = logging.getLogger(__name__)


# Role-family classification for where to apply which EQ moves
_BASS_LIKE = {"sub_bass", "bass", "bass_guitar", "bass_808", "growl_bass", "reese_bass"}
_VOCAL_LIKE = {"vocal_lead", "vocal_backup", "vocal_chop"}
_LEAD_LIKE = {"lead_synth", "lead_guitar"}
_DRUM_LIKE = {"kick", "snare", "clap", "hats", "open_hat", "perc", "toms", "cymbals"}


# Name-based fallback classification if track isn't matched to a known role
_BASS_KEYWORDS = ("sub", "808", "bass")
_VOCAL_KEYWORDS = ("vox", "vocal", "voc", " bg ")
_LEAD_KEYWORDS = ("lead",)
_DRUM_KEYWORDS = ("kick", "snare", "hat", "clap", "perc", "drum", "tom", "cymbal")


def _classify_track(name: str, resolved_role: str | None) -> str:
    """Return 'bass' | 'vocal' | 'lead' | 'drum' | 'other'.

    Role-based classification wins first (most authoritative). Keyword fallback
    uses LONGEST-match-wins so names like "Kick Bass" classify as drum (kick=4)
    rather than bass (bass=4, tie → kick wins due to _DRUM_KEYWORDS coming first
    in the keyword_sets list order below, which matches "kick" fully vs "bass"
    fully — but we resolve ties by keyword specificity).
    """
    if resolved_role:
        if resolved_role in _BASS_LIKE:
            return "bass"
        if resolved_role in _VOCAL_LIKE:
            return "vocal"
        if resolved_role in _LEAD_LIKE:
            return "lead"
        if resolved_role in _DRUM_LIKE:
            return "drum"

    n = name.lower()
    # (keyword_set, classification) — evaluated all together, longest match wins.
    keyword_sets = [
        (_DRUM_KEYWORDS, "drum"),     # drums beat bass for "kick bass" etc.
        (_VOCAL_KEYWORDS, "vocal"),
        (_LEAD_KEYWORDS, "lead"),
        (_BASS_KEYWORDS, "bass"),
    ]
    best_kind = "other"
    best_len = 0
    for kw_set, kind in keyword_sets:
        for kw in kw_set:
            if kw in n and len(kw) > best_len:
                best_kind = kind
                best_len = len(kw)
    return best_kind


async def run_fix_mix(client, style: str = "", include_master: bool = True) -> dict:
    """Apply a corrective EQ + master limiter pass.

    If `style` is a known v2 catalog style, use its aliases to classify tracks
    more accurately. Otherwise fall back to keyword classification on the
    track name.
    """
    # Load catalog for role classification if style given
    role_map: dict[int, str] = {}
    style_profile = None
    if style:
        import reaper_mcp.mix_engine.catalog  # noqa: F401
        from reaper_mcp.mix_engine.profiles_v2 import get_profile, resolve_roles
        style_profile = get_profile(style)

    # Get live tracks
    live = await client.execute("track_get_all")
    live_data = live.get("data", live)
    live_tracks = live_data.get("tracks", [])
    if not live_tracks:
        return {"success": False, "error": "No tracks in project"}

    if style_profile is not None:
        from reaper_mcp.mix_engine.profiles_v2 import resolve_roles
        role_map = resolve_roles(style_profile, live_tracks)

    # Detect plugin suite (for EQ plugin name)
    suite = await detect_plugins(client)
    plugin_profile = get_plugin_profile(suite)

    # Build per-track EQ
    tracks_with_eq = []
    classifications = {"bass": 0, "vocal": 0, "lead": 0, "drum": 0, "other": 0}

    for track in live_tracks:
        ti = int(track["index"])
        name = track.get("name", "") or ""
        if not name:
            continue  # skip unnamed tracks
        # Skip any MIX:* bus tracks we might have created
        if name.startswith("MIX:") or name.startswith("FIX:"):
            continue

        role = role_map.get(ti)
        kind = _classify_track(name, role)
        classifications[kind] = classifications.get(kind, 0) + 1

        eq_profile = _build_corrective_eq(kind)
        if eq_profile is None:
            continue

        fx_entry = plugin_profile.eq_fx_chain_entry(eq_profile)
        tracks_with_eq.append({"track_index": ti, "fx_chain": [fx_entry]})

    if tracks_with_eq:
        await client.execute("setup_fx_chain", tracks=json.dumps(tracks_with_eq))

    # Apply master limiter + gentle glue comp
    master_summary = None
    if include_master:
        master_summary = await _apply_emergency_master(client, style_profile, suite)

    return {
        "success": True,
        "plugin_suite": suite.value,
        "tracks_processed": len(tracks_with_eq),
        "classifications": classifications,
        "master": master_summary,
    }


def _build_corrective_eq(kind: str) -> dict | None:
    """Build a legacy-dict EQ profile for the given track classification."""
    if kind == "bass":
        # Don't HP bass; just cut mud
        return {
            "hp_freq": 20,
            "cuts": [{"freq": 250, "gain_db": -2.0, "q": 2.0}],
            "boosts": [],
        }
    if kind == "vocal":
        return {
            "hp_freq": 100,
            "cuts": [
                {"freq": 250, "gain_db": -2.5, "q": 1.8},
                {"freq": 3000, "gain_db": -2.0, "q": 3.0},  # tame harshness
            ],
            "boosts": [
                {"freq": 12000, "gain_db": 1.5, "q": 0.8, "shape": "high_shelf"},
            ],
        }
    if kind == "lead":
        return {
            "hp_freq": 120,
            "cuts": [
                {"freq": 250, "gain_db": -2.0, "q": 2.0},
                {"freq": 3500, "gain_db": -1.5, "q": 3.0},
            ],
            "boosts": [
                {"freq": 12000, "gain_db": 1.0, "q": 0.8, "shape": "high_shelf"},
            ],
        }
    if kind == "drum":
        return {
            "hp_freq": 30,
            "cuts": [{"freq": 400, "gain_db": -1.5, "q": 1.5}],
            "boosts": [
                {"freq": 12000, "gain_db": 1.0, "q": 0.8, "shape": "high_shelf"},
            ],
        }
    # Other (pads, chords, piano) — mild HP + mud cut
    return {
        "hp_freq": 80,
        "cuts": [{"freq": 250, "gain_db": -2.0, "q": 1.8}],
        "boosts": [],
    }


async def _apply_emergency_master(client, style_profile, suite) -> dict:
    """Apply a gentle master chain — glue comp + limiter."""
    from reaper_mcp.mix_engine.profiles_v2 import MasteringChain, CompProfile
    from reaper_mcp.mix_engine.master import _build_master_fx_chain

    # Use the style's mastering profile if available, else a neutral default
    if style_profile is not None and style_profile.mastering is not None:
        spec = style_profile.mastering
    else:
        spec = MasteringChain(
            target_lufs=-10.0,
            true_peak_db=-1.0,
            stereo_width=1.0,
            limiter_character="transparent",
            low_shelf_db=0.0,
            high_shelf_db=0.0,
            bus_comp=CompProfile(
                threshold_db=-10.0, ratio=1.8,
                attack_ms=30.0, release_ms=200.0,
                makeup_db=1.0, knee_db=6.0,
            ),
        )

    fx_chain = _build_master_fx_chain(spec, suite)
    result = await client.execute(
        "setup_master_chain",
        fx_chain=json.dumps(fx_chain),
        clean=True,
    )
    data = result.get("data", result)
    return {
        "target_lufs": spec.target_lufs,
        "true_peak_db": spec.true_peak_db,
        "fx_added": data.get("fx_added", []),
    }
