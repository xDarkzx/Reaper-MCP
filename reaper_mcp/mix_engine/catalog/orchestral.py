"""Orchestral / cinematic style profiles — 3 subgenres. Pairs with the
BBC Spitfire CC guidance in 00_core.md (CC1-driven dynamics, keyswitch
articulations) — these are the mixing targets for music composed that way.

Defining techniques: near-zero bus compression (dynamics come from the
performance/CC1 automation, not a limiter), wide true-peak headroom, natural
hall reverb tails, no sidechain. Loudness targets sit well below pop/EDM —
cinema and broadcast delivery specs are quieter by design (see
reaper_mcp/tools/analysis_tools.py's _LUFS_REFERENCE for the same numbers).

NOTE: these are consolidated-section profiles (one "strings"/"brass"/
"woodwinds"/"choir" track each). For a full per-instrument multi-mic template
(separate Violin 1/2, Viola, Cello, individual winds/brass), use the legacy
orchestral path instead — pass a style name that ISN'T one of the three
below (empty string works) and it matches VSTi/instrument names in
../profiles.py, which has real per-instrument EQ/comp tuning these three
generic profiles don't attempt to replicate.
"""

from reaper_mcp.mix_engine.profiles_v2 import (
    StyleProfile, InstrumentRole, MasteringChain, ReverbBus, ReverbSend,
    register_profile,
)
from reaper_mcp.mix_engine.catalog._shared import (
    strings_section, brass_orchestral, woodwinds, timpani_perc, choir,
    piano_jazz,
    comp_orchestral_glue,
    default_aliases,
)


# ═════════════════════════════════════════════════════════════════
# CLASSICAL / CHAMBER — acoustic ensemble, maximum dynamic range,
# minimal-to-no processing. The performance and the room ARE the mix.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="classical_chamber",
    family="orchestral",
    bpm_range=(50, 160),
    key_hints=["major", "minor"],
    instrument_roles={
        "strings_section": InstrumentRole(eq=strings_section(), volume_db=-3.0,
                                           sends=[ReverbSend("hall", -6.0)]),
        "woodwinds":       InstrumentRole(eq=woodwinds(), volume_db=-4.0, pan=0.15,
                                           sends=[ReverbSend("hall", -7.0)]),
        "brass_orchestral": InstrumentRole(eq=brass_orchestral(), volume_db=-5.0, pan=-0.15,
                                            sends=[ReverbSend("hall", -7.0)]),
        "piano":           InstrumentRole(eq=piano_jazz(), volume_db=-4.0,
                                           sends=[ReverbSend("hall", -6.0)]),
    },
    aliases=default_aliases(["strings_section", "woodwinds", "brass_orchestral", "piano"]),
    sidechain=[],
    reverb_buses={
        # Concert-hall reverb — long, dense, natural. This IS the space.
        "hall": ReverbBus(room_size=0.95, dampening=0.20, wet_db=-5, lowpass_hz=13000,
                           hipass_hz=80, width=1.3, color=(70,130,200)),
    },
    mastering=MasteringChain(
        # No bus_comp at all — a real chamber mix has zero glue compression.
        # -20 LUFS / -2 dBTP leaves the full dynamic range of a quiet passage
        # to a full tutti intact; this is closer to a classical CD master
        # than a streaming-loudness target, and that's intentional.
        target_lufs=-20.0, true_peak_db=-2.0, stereo_width=1.2, limiter_character="transparent",
        low_shelf_db=0.0, low_shelf_freq=80, high_shelf_db=0.5, high_shelf_freq=12000,
        bus_comp=None,
    ),
    structure_hints=["movement_1", "movement_2", "movement_3"],
))


# ═════════════════════════════════════════════════════════════════
# CINEMATIC / TRAILER — hybrid orchestral + percussion hits + choir,
# built for tension/build/impact. Slightly more controlled than pure
# classical but still dynamics-first — no pumping, no brickwall.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="cinematic_trailer",
    family="orchestral",
    bpm_range=(60, 150),
    key_hints=["minor", "phrygian", "locrian"],
    instrument_roles={
        "strings_section": InstrumentRole(eq=strings_section(), comp=comp_orchestral_glue(), volume_db=-3.0,
                                           sends=[ReverbSend("hall", -5.0)]),
        "brass_orchestral": InstrumentRole(eq=brass_orchestral(), comp=comp_orchestral_glue(), volume_db=-3.0,
                                            sends=[ReverbSend("hall", -6.0)]),
        "choir":           InstrumentRole(eq=choir(), comp=comp_orchestral_glue(), volume_db=-4.0,
                                           sends=[ReverbSend("hall", -5.0)]),
        "timpani_perc":    InstrumentRole(eq=timpani_perc(), comp=comp_orchestral_glue(), volume_db=-2.0,
                                           sends=[ReverbSend("hall", -7.0)]),
    },
    aliases=default_aliases(["strings_section", "brass_orchestral", "choir", "timpani_perc"]),
    sidechain=[],
    reverb_buses={
        "hall": ReverbBus(room_size=0.92, dampening=0.22, wet_db=-4, lowpass_hz=14000,
                           hipass_hz=90, width=1.3, color=(70,130,200)),
    },
    mastering=MasteringChain(
        # Trailer masters run louder than concert-hall classical (they compete
        # in a trailer-house reel) but still nowhere near pop/EDM — headroom
        # for the impact hits to actually hit is the whole point.
        target_lufs=-16.0, true_peak_db=-1.0, stereo_width=1.25, limiter_character="transparent",
        low_shelf_db=1.0, low_shelf_freq=60, high_shelf_db=0.5, high_shelf_freq=12000,
        bus_comp=comp_orchestral_glue(),
    ),
    structure_hints=["tension_build", "drop_hit", "breakdown", "second_build", "climax", "resolve"],
))


# ═════════════════════════════════════════════════════════════════
# AMBIENT ORCHESTRAL — sustained pads/drones from real sections,
# huge reverb tails, essentially no transients to preserve.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="ambient_orchestral",
    family="orchestral",
    bpm_range=(50, 90),
    key_hints=["dorian", "lydian", "minor", "major"],
    instrument_roles={
        "strings_section": InstrumentRole(eq=strings_section(), volume_db=-4.0,
                                           sends=[ReverbSend("hall", -3.0)]),
        "choir":           InstrumentRole(eq=choir(), volume_db=-6.0,
                                           sends=[ReverbSend("hall", -3.0)]),
        "woodwinds":       InstrumentRole(eq=woodwinds(), volume_db=-6.0,
                                           sends=[ReverbSend("hall", -4.0)]),
    },
    aliases=default_aliases(["strings_section", "choir", "woodwinds"]),
    sidechain=[],
    reverb_buses={
        "hall": ReverbBus(room_size=0.98, dampening=0.15, wet_db=-3, lowpass_hz=13000,
                           hipass_hz=60, width=1.4, color=(70,130,200)),
    },
    mastering=MasteringChain(
        target_lufs=-20.0, true_peak_db=-2.0, stereo_width=1.3, limiter_character="transparent",
        low_shelf_db=0.0, low_shelf_freq=60, high_shelf_db=0.0, high_shelf_freq=12000,
        bus_comp=None,
    ),
    structure_hints=["swell_in", "sustain", "swell_out"],
))
