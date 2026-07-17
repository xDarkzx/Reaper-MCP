"""Jazz style profiles — 3 subgenres. The defining technique across all of
them: dynamics are the performance, not something to flatten. Every comp
here is gentle-to-nonexistent; the point is to glue and clean up, never to
squash. No sidechain anywhere — jazz has no pumping aesthetic.
"""

from reaper_mcp.mix_engine.profiles_v2 import (
    StyleProfile, InstrumentRole, MasteringChain, ReverbBus, ReverbSend,
    register_profile, DEFAULT_REVERB_BUSES,
)
from reaper_mcp.mix_engine.catalog._shared import (
    kick_acoustic, snare_acoustic, hats, ride_cymbal,
    upright_bass, bass_guitar, piano_jazz, clean_guitar,
    vocal_jazz, horns_section,
    comp_jazz_gentle, comp_horns, comp_master_transparent,
    default_aliases,
)


# ═════════════════════════════════════════════════════════════════
# TRADITIONAL / SWING JAZZ — acoustic trio/quartet, brushes, upright bass.
# Wide dynamic range, natural room ambience, minimal processing throughout.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="swing_jazz",
    family="jazz",
    bpm_range=(100, 220),  # swing tempo varies hugely, walking ballad to bebop burner
    key_hints=["major", "dorian", "mixolydian", "minor"],
    instrument_roles={
        "kick":          InstrumentRole(eq=kick_acoustic(), volume_db=-8.0),
        "snare":         InstrumentRole(eq=snare_acoustic(), volume_db=-7.0,
                                         sends=[ReverbSend("room", -10.0)]),
        "hats":          InstrumentRole(eq=hats(), volume_db=-11.0, pan=0.2),
        "ride":          InstrumentRole(eq=ride_cymbal(), volume_db=-6.0, pan=0.15,
                                         sends=[ReverbSend("room", -12.0)]),
        "upright_bass":  InstrumentRole(eq=upright_bass(), comp=comp_jazz_gentle(), volume_db=-4.0),
        "piano":         InstrumentRole(eq=piano_jazz(), comp=comp_jazz_gentle(), volume_db=-3.0, pan=-0.15,
                                         sends=[ReverbSend("room", -10.0)]),
        "vocal_lead":    InstrumentRole(eq=vocal_jazz(), comp=comp_jazz_gentle(), volume_db=-2.0,
                                         sends=[ReverbSend("room", -9.0), ReverbSend("plate", -14.0)]),
        "horns_section": InstrumentRole(eq=horns_section(), comp=comp_horns(), volume_db=-3.0, pan=0.2,
                                         sends=[ReverbSend("room", -9.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "ride", "upright_bass",
                              "piano", "vocal_lead", "horns_section"]),
    sidechain=[],
    reverb_buses={
        # Small-room jazz-club ambience by default — intimate, not washy.
        "room":  ReverbBus(room_size=0.5, dampening=0.4, wet_db=-8, lowpass_hz=11000, hipass_hz=150, width=1.1, color=(70,180,70)),
        "hall":  DEFAULT_REVERB_BUSES["hall"],
        "plate": DEFAULT_REVERB_BUSES["plate"],
    },
    mastering=MasteringChain(
        # Wide dynamic range on purpose — jazz masters sit well below the
        # loudness-war targets other genres chase. -16 LUFS is a listenable,
        # dynamics-preserving target for streaming without gutting the mix.
        target_lufs=-16.0, true_peak_db=-1.0, stereo_width=1.1, limiter_character="transparent",
        low_shelf_db=0.0, low_shelf_freq=80, high_shelf_db=0.5, high_shelf_freq=11000,
        bus_comp=comp_jazz_gentle(),
    ),
    structure_hints=["head", "solo_1", "solo_2", "solo_3", "trading_fours", "head_out"],
))


# ═════════════════════════════════════════════════════════════════
# JAZZ FUSION — electric, bigger drums, more low-end weight, still dynamic.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="jazz_fusion",
    family="jazz",
    bpm_range=(90, 160),
    key_hints=["dorian", "lydian", "minor", "mixolydian"],
    instrument_roles={
        "kick":          InstrumentRole(eq=kick_acoustic(), comp=comp_jazz_gentle(), volume_db=-4.0),
        "snare":         InstrumentRole(eq=snare_acoustic(), comp=comp_jazz_gentle(), volume_db=-4.0,
                                         sends=[ReverbSend("room", -9.0)]),
        "hats":          InstrumentRole(eq=hats(), volume_db=-10.0, pan=0.2),
        "ride":          InstrumentRole(eq=ride_cymbal(), volume_db=-7.0, pan=0.15,
                                         sends=[ReverbSend("room", -12.0)]),
        "bass_guitar":   InstrumentRole(eq=bass_guitar(), comp=comp_jazz_gentle(), volume_db=-4.0),
        "piano":         InstrumentRole(eq=piano_jazz(), comp=comp_jazz_gentle(), volume_db=-4.0, pan=-0.2,
                                         sends=[ReverbSend("room", -10.0)]),
        "clean_guitar":  InstrumentRole(eq=clean_guitar(), comp=comp_jazz_gentle(), volume_db=-5.0, pan=0.25,
                                         sends=[ReverbSend("plate", -11.0)]),
        "horns_section": InstrumentRole(eq=horns_section(), comp=comp_horns(), volume_db=-4.0,
                                         sends=[ReverbSend("room", -9.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "ride", "bass_guitar",
                              "piano", "clean_guitar", "horns_section"]),
    sidechain=[],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-13.0, true_peak_db=-1.0, stereo_width=1.15, limiter_character="transparent",
        low_shelf_db=0.5, low_shelf_freq=70, high_shelf_db=1.0, high_shelf_freq=11000,
        bus_comp=comp_jazz_gentle(),
    ),
    structure_hints=["head", "solo_1", "solo_2", "vamp", "head_out"],
))


# ═════════════════════════════════════════════════════════════════
# LATIN / BOSSA JAZZ — nylon guitar, brushed kit, warm and relaxed.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="latin_jazz",
    family="jazz",
    bpm_range=(70, 130),
    key_hints=["major", "minor", "dorian"],
    instrument_roles={
        "kick":          InstrumentRole(eq=kick_acoustic(), volume_db=-7.0),
        "snare":         InstrumentRole(eq=snare_acoustic(), volume_db=-8.0,
                                         sends=[ReverbSend("room", -10.0)]),
        "hats":          InstrumentRole(eq=hats(), volume_db=-11.0, pan=0.2),
        "ride":          InstrumentRole(eq=ride_cymbal(), volume_db=-8.0, pan=0.15),
        "upright_bass":  InstrumentRole(eq=upright_bass(), comp=comp_jazz_gentle(), volume_db=-5.0),
        "piano":         InstrumentRole(eq=piano_jazz(), comp=comp_jazz_gentle(), volume_db=-4.0, pan=-0.15,
                                         sends=[ReverbSend("room", -9.0)]),
        "clean_guitar":  InstrumentRole(eq=clean_guitar(), comp=comp_jazz_gentle(), volume_db=-4.0, pan=0.2,
                                         sends=[ReverbSend("room", -9.0)]),
        "vocal_lead":    InstrumentRole(eq=vocal_jazz(), comp=comp_jazz_gentle(), volume_db=-2.0,
                                         sends=[ReverbSend("room", -9.0), ReverbSend("plate", -13.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "ride", "upright_bass",
                              "piano", "clean_guitar", "vocal_lead"]),
    sidechain=[],
    reverb_buses={
        "room":  ReverbBus(room_size=0.55, dampening=0.35, wet_db=-8, lowpass_hz=11000, hipass_hz=140, width=1.1, color=(70,180,70)),
        "hall":  DEFAULT_REVERB_BUSES["hall"],
        "plate": DEFAULT_REVERB_BUSES["plate"],
    },
    mastering=MasteringChain(
        target_lufs=-14.0, true_peak_db=-1.0, stereo_width=1.1, limiter_character="transparent",
        low_shelf_db=0.0, low_shelf_freq=80, high_shelf_db=0.5, high_shelf_freq=11000,
        bus_comp=comp_jazz_gentle(),
    ),
    structure_hints=["head", "solo_1", "solo_2", "head_out"],
))
