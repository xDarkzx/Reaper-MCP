"""Rock style profiles — 6 subgenres from classic to punk to post-rock."""

from reaper_mcp.mix_engine.profiles_v2 import (
    StyleProfile, InstrumentRole, SidechainSpec, MasteringChain, ReverbBus, ReverbSend,
    EQBand, register_profile, DEFAULT_REVERB_BUSES,
)
from reaper_mcp.mix_engine.catalog._shared import (
    kick_acoustic, snare_acoustic, hats, perc_bright, drums_bus,
    bass_guitar, rhythm_guitar, lead_guitar, clean_guitar,
    piano_modern, vocal_lead, vocal_backup, pad,
    comp_kick_edm, comp_snare_edm, comp_bass_edm, comp_vocal, comp_pad,
    comp_drums_bus, comp_master_glue, comp_master_transparent,
    default_aliases,
)


# ═════════════════════════════════════════════════════════════════
# ALT ROCK — modern indie/alt, punchy drums, prominent vocal.
# -10 LUFS. Stereo guitars panned hard. Light bus glue.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="alt_rock",
    family="rock",
    bpm_range=(110, 145),
    key_hints=["minor", "major", "mixolydian"],
    instrument_roles={
        "kick":          InstrumentRole(eq=kick_acoustic(), comp=comp_kick_edm(), volume_db=-2.0),
        "snare":         InstrumentRole(eq=snare_acoustic(), comp=comp_snare_edm(), volume_db=-3.0,
                                         sends=[ReverbSend("plate", -8.0), ReverbSend("room", -12.0)]),
        "hats":          InstrumentRole(eq=hats(), volume_db=-10.0, pan=0.25,
                                         sends=[ReverbSend("room", -15.0)]),
        "toms":          InstrumentRole(eq=perc_bright(), comp=comp_snare_edm(), volume_db=-6.0,
                                         sends=[ReverbSend("room", -8.0)]),
        "cymbals":       InstrumentRole(eq=hats(), volume_db=-12.0,
                                         sends=[ReverbSend("room", -12.0)]),
        "bass_guitar":   InstrumentRole(eq=bass_guitar(), comp=comp_bass_edm(), volume_db=-3.0),
        "rhythm_guitar": InstrumentRole(eq=rhythm_guitar(), volume_db=-5.0, pan=-0.5,
                                         sends=[ReverbSend("plate", -12.0)]),
        "lead_guitar":   InstrumentRole(eq=lead_guitar(), volume_db=-4.0, pan=0.3,
                                         sends=[ReverbSend("plate", -8.0), ReverbSend("hall", -14.0)]),
        "clean_guitar":  InstrumentRole(eq=clean_guitar(), volume_db=-6.0, pan=0.2,
                                         sends=[ReverbSend("plate", -10.0)]),
        "piano":         InstrumentRole(eq=piano_modern(), volume_db=-6.0,
                                         sends=[ReverbSend("hall", -10.0)]),
        "vocal_lead":    InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-3.0,
                                         sends=[ReverbSend("plate", -10.0), ReverbSend("hall", -14.0)]),
        "vocal_backup":  InstrumentRole(eq=vocal_backup(), comp=comp_vocal(), volume_db=-7.0, pan=-0.2,
                                         sends=[ReverbSend("plate", -8.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "toms", "cymbals",
                              "bass_guitar", "rhythm_guitar", "lead_guitar", "clean_guitar",
                              "piano", "vocal_lead", "vocal_backup"]),
    sidechain=[],  # no sidechain in rock
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-10.0, true_peak_db=-1.0, stereo_width=1.0, limiter_character="warm",
        low_shelf_db=0.5, low_shelf_freq=80, high_shelf_db=1.0, high_shelf_freq=11000,
        bus_comp=comp_master_glue(),
    ),
    structure_hints=["intro", "verse", "chorus", "verse2", "chorus2", "bridge", "chorus3", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# CLASSIC ROCK — 70s warmth, prominent snare, analog glue.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="classic_rock",
    family="rock",
    bpm_range=(90, 130),
    key_hints=["major", "mixolydian", "minor"],
    instrument_roles={
        "kick":          InstrumentRole(eq=kick_acoustic(), comp=comp_kick_edm(), volume_db=-3.0),
        "snare":         InstrumentRole(eq=snare_acoustic(), comp=comp_snare_edm(), volume_db=-2.0,
                                         sends=[ReverbSend("room", -7.0), ReverbSend("plate", -10.0)]),
        "hats":          InstrumentRole(eq=hats(), volume_db=-11.0, pan=0.25,
                                         sends=[ReverbSend("room", -14.0)]),
        "toms":          InstrumentRole(eq=perc_bright(), volume_db=-6.0,
                                         sends=[ReverbSend("room", -8.0)]),
        "cymbals":       InstrumentRole(eq=hats(), volume_db=-12.0,
                                         sends=[ReverbSend("room", -10.0)]),
        "bass_guitar":   InstrumentRole(eq=bass_guitar(), comp=comp_bass_edm(), volume_db=-4.0),
        "rhythm_guitar": InstrumentRole(eq=rhythm_guitar(), volume_db=-4.0, pan=-0.6,
                                         sends=[ReverbSend("plate", -10.0)]),
        "lead_guitar":   InstrumentRole(eq=lead_guitar(), volume_db=-3.0, pan=0.4,
                                         sends=[ReverbSend("plate", -7.0), ReverbSend("hall", -12.0)]),
        "piano":         InstrumentRole(eq=piano_modern(), volume_db=-6.0,
                                         sends=[ReverbSend("hall", -10.0), ReverbSend("plate", -12.0)]),
        "vocal_lead":    InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-3.0,
                                         sends=[ReverbSend("plate", -8.0), ReverbSend("hall", -12.0)]),
        "vocal_backup":  InstrumentRole(eq=vocal_backup(), comp=comp_vocal(), volume_db=-7.0,
                                         sends=[ReverbSend("plate", -8.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "toms", "cymbals",
                              "bass_guitar", "rhythm_guitar", "lead_guitar",
                              "piano", "vocal_lead", "vocal_backup"]),
    sidechain=[],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-11.0, true_peak_db=-1.0, stereo_width=1.0, limiter_character="warm",
        low_shelf_db=0.5, low_shelf_freq=80, high_shelf_db=0.5, high_shelf_freq=10000,
        bus_comp=comp_master_glue(),
    ),
    structure_hints=["intro", "verse", "chorus", "verse2", "chorus2", "solo", "chorus3", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# POP ROCK — polished, vocal-forward, punchy drums.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="pop_rock",
    family="rock",
    bpm_range=(100, 140),
    key_hints=["major", "minor"],
    instrument_roles={
        "kick":          InstrumentRole(eq=kick_acoustic(), comp=comp_kick_edm(), volume_db=-2.0),
        "snare":         InstrumentRole(eq=snare_acoustic(), comp=comp_snare_edm(), volume_db=-2.0,
                                         sends=[ReverbSend("plate", -8.0)]),
        "hats":          InstrumentRole(eq=hats(), volume_db=-10.0, pan=0.2),
        "toms":          InstrumentRole(eq=perc_bright(), volume_db=-6.0,
                                         sends=[ReverbSend("room", -10.0)]),
        "cymbals":       InstrumentRole(eq=hats(), volume_db=-11.0),
        "bass_guitar":   InstrumentRole(eq=bass_guitar(), comp=comp_bass_edm(), volume_db=-3.0),
        "rhythm_guitar": InstrumentRole(eq=rhythm_guitar(), volume_db=-5.0, pan=-0.5,
                                         sends=[ReverbSend("plate", -12.0)]),
        "lead_guitar":   InstrumentRole(eq=lead_guitar(), volume_db=-4.0, pan=0.3,
                                         sends=[ReverbSend("plate", -8.0)]),
        "clean_guitar":  InstrumentRole(eq=clean_guitar(), volume_db=-6.0, pan=0.2,
                                         sends=[ReverbSend("plate", -10.0)]),
        "piano":         InstrumentRole(eq=piano_modern(), volume_db=-6.0,
                                         sends=[ReverbSend("hall", -10.0)]),
        "pad":           InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-10.0,
                                         sends=[ReverbSend("hall", -8.0)]),
        "vocal_lead":    InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-2.0,
                                         sends=[ReverbSend("plate", -8.0), ReverbSend("hall", -14.0)]),
        "vocal_backup":  InstrumentRole(eq=vocal_backup(), comp=comp_vocal(), volume_db=-7.0,
                                         sends=[ReverbSend("plate", -8.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "toms", "cymbals",
                              "bass_guitar", "rhythm_guitar", "lead_guitar", "clean_guitar",
                              "piano", "pad", "vocal_lead", "vocal_backup"]),
    sidechain=[],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-9.0, true_peak_db=-1.0, stereo_width=1.05, limiter_character="transparent",
        low_shelf_db=0.5, low_shelf_freq=80, high_shelf_db=1.0, high_shelf_freq=11000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "verse", "pre_chorus", "chorus", "verse2", "pre_chorus2", "chorus2",
                      "bridge", "chorus3", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# HARD ROCK / METAL — scooped guitars, tight kick, aggressive mids cut.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="hard_rock",
    family="rock",
    bpm_range=(100, 180),
    key_hints=["minor", "phrygian", "locrian"],
    instrument_roles={
        "kick":          InstrumentRole(eq=kick_acoustic(), comp=comp_kick_edm(), volume_db=-1.0),
        "snare":         InstrumentRole(eq=snare_acoustic(), comp=comp_snare_edm(), volume_db=-1.0,
                                         sends=[ReverbSend("room", -10.0)]),
        "hats":          InstrumentRole(eq=hats(), volume_db=-11.0, pan=0.2),
        "toms":          InstrumentRole(eq=perc_bright(), volume_db=-5.0,
                                         sends=[ReverbSend("room", -10.0)]),
        "cymbals":       InstrumentRole(eq=hats(), volume_db=-12.0),
        "bass_guitar":   InstrumentRole(eq=bass_guitar(), comp=comp_bass_edm(), volume_db=-3.0),
        "rhythm_guitar": InstrumentRole(
            eq=rhythm_guitar(), volume_db=-3.0, pan=-0.7,
            sends=[ReverbSend("plate", -14.0)],
        ),
        "lead_guitar":   InstrumentRole(eq=lead_guitar(), volume_db=-3.0, pan=0.5,
                                         sends=[ReverbSend("plate", -10.0)]),
        "vocal_lead":    InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-2.0,
                                         sends=[ReverbSend("plate", -9.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "toms", "cymbals",
                              "bass_guitar", "rhythm_guitar", "lead_guitar", "vocal_lead"]),
    sidechain=[],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-8.0, true_peak_db=-1.0, stereo_width=1.05, limiter_character="aggressive",
        low_shelf_db=1.0, low_shelf_freq=70, high_shelf_db=0.5, high_shelf_freq=10000,
        bus_comp=comp_master_glue(),
    ),
    structure_hints=["intro", "verse", "chorus", "verse2", "chorus2", "solo", "chorus3", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# PUNK — fast, raw, minimal processing, slight mid boost.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="punk",
    family="rock",
    bpm_range=(140, 200),
    key_hints=["major", "minor"],
    instrument_roles={
        "kick":          InstrumentRole(eq=kick_acoustic(), comp=comp_kick_edm(), volume_db=-2.0),
        "snare":         InstrumentRole(eq=snare_acoustic(), comp=comp_snare_edm(), volume_db=-1.0,
                                         sends=[ReverbSend("room", -12.0)]),
        "hats":          InstrumentRole(eq=hats(), volume_db=-10.0, pan=0.2),
        "cymbals":       InstrumentRole(eq=hats(), volume_db=-11.0),
        "bass_guitar":   InstrumentRole(eq=bass_guitar(), comp=comp_bass_edm(), volume_db=-3.0),
        "rhythm_guitar": InstrumentRole(eq=rhythm_guitar(), volume_db=-3.0, pan=-0.4,
                                         sends=[ReverbSend("room", -14.0)]),
        "vocal_lead":    InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-2.0,
                                         sends=[ReverbSend("room", -10.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "cymbals",
                              "bass_guitar", "rhythm_guitar", "vocal_lead"]),
    sidechain=[],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-9.0, true_peak_db=-1.0, stereo_width=1.0, limiter_character="aggressive",
        low_shelf_db=0.5, low_shelf_freq=80, high_shelf_db=0.5, high_shelf_freq=10000,
        bus_comp=comp_master_glue(),
    ),
    structure_hints=["intro", "verse", "chorus", "verse2", "chorus2", "bridge", "chorus3"],
))


# ═════════════════════════════════════════════════════════════════
# POST ROCK — cinematic, ambient guitars, huge reverb tails.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="post_rock",
    family="rock",
    bpm_range=(60, 120),
    key_hints=["minor", "major", "dorian"],
    instrument_roles={
        "kick":          InstrumentRole(eq=kick_acoustic(), comp=comp_kick_edm(), volume_db=-4.0),
        "snare":         InstrumentRole(eq=snare_acoustic(), comp=comp_snare_edm(), volume_db=-4.0,
                                         sends=[ReverbSend("hall", -5.0), ReverbSend("plate", -8.0)]),
        "hats":          InstrumentRole(eq=hats(), volume_db=-11.0, pan=0.15),
        "toms":          InstrumentRole(eq=perc_bright(), volume_db=-7.0,
                                         sends=[ReverbSend("hall", -7.0)]),
        "cymbals":       InstrumentRole(eq=hats(), volume_db=-10.0,
                                         sends=[ReverbSend("hall", -8.0)]),
        "bass_guitar":   InstrumentRole(eq=bass_guitar(), comp=comp_bass_edm(), volume_db=-4.0),
        "rhythm_guitar": InstrumentRole(eq=rhythm_guitar(), volume_db=-5.0, pan=-0.5,
                                         sends=[ReverbSend("hall", -6.0), ReverbSend("plate", -10.0)]),
        "lead_guitar":   InstrumentRole(eq=lead_guitar(), volume_db=-4.0, pan=0.5,
                                         sends=[ReverbSend("hall", -4.0), ReverbSend("plate", -8.0)]),
        "clean_guitar":  InstrumentRole(eq=clean_guitar(), volume_db=-6.0, pan=0.3,
                                         sends=[ReverbSend("hall", -5.0), ReverbSend("plate", -10.0)]),
        "piano":         InstrumentRole(eq=piano_modern(), volume_db=-6.0,
                                         sends=[ReverbSend("hall", -6.0)]),
        "pad":           InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-8.0,
                                         sends=[ReverbSend("hall", -4.0)]),
        "vocal_lead":    InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-5.0,
                                         sends=[ReverbSend("hall", -6.0), ReverbSend("plate", -10.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "toms", "cymbals",
                              "bass_guitar", "rhythm_guitar", "lead_guitar", "clean_guitar",
                              "piano", "pad", "vocal_lead"]),
    sidechain=[],
    reverb_buses={
        "hall":  ReverbBus(room_size=0.90, dampening=0.25, wet_db=-4, lowpass_hz=14000, hipass_hz=120, width=1.3, color=(70,130,200)),
        "room":  ReverbBus(room_size=0.55, dampening=0.45, wet_db=-7, lowpass_hz=11000, hipass_hz=180, width=1.0, color=(70,180,70)),
        "plate": ReverbBus(room_size=0.70, dampening=0.20, wet_db=-5, lowpass_hz=17000, hipass_hz=250, width=1.3, color=(160,70,180)),
    },
    mastering=MasteringChain(
        target_lufs=-13.0, true_peak_db=-1.0, stereo_width=1.2, limiter_character="transparent",
        low_shelf_db=0.5, low_shelf_freq=80, high_shelf_db=1.0, high_shelf_freq=11000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "build", "peak", "decay", "build2", "peak2", "outro"],
))
