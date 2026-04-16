"""EDM style profiles — 11 subgenres covering festival to emotional to heavy.

All EDM styles share the same role vocabulary: kick, sub_bass, bass, lead_synth,
pluck_synth, pad, vocal_chop, vocal_lead, snare, hats, perc, riser_fx, impact_fx.

Key genre differences:
  - Kick weight + click: festival=punchy, dubstep=weighty, house=clean click
  - Sidechain intensity: big_room≫deep_house, dubstep=none-on-drop
  - Target LUFS: festival loud (-6), deep house preserves dynamics (-10)
  - Reverb: future_bass/melodic_dubstep use bright plate; tech_house dry
"""

from reaper_mcp.mix_engine.profiles_v2 import (
    StyleProfile, InstrumentRole, SidechainSpec, MasteringChain, ReverbBus, ReverbSend,
    CompProfile, EQBand, register_profile, DEFAULT_REVERB_BUSES,
)
from reaper_mcp.mix_engine.catalog._shared import (
    kick_edm, snare_edm, hats, perc_bright, sub_bass, mid_bass, bass_808,
    lead_synth, pluck_synth, pad, chord_stab, piano_modern,
    vocal_lead, vocal_chop, riser_fx, impact_fx,
    comp_kick_edm, comp_snare_edm, comp_bass_edm, comp_vocal, comp_lead_synth,
    comp_pad, comp_master_transparent, comp_master_glue,
    default_aliases,
)


# ═════════════════════════════════════════════════════════════════
# MELODIC DUBSTEP / CHILLSTEP — emotional, piano + vocal chops into
# dubstep drop. -8 LUFS. Heavy pad sidechain. Bright plate reverb.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="melodic_dubstep",
    family="edm",
    bpm_range=(140, 150),  # half-time feel ~70-75 bpm
    key_hints=["minor", "harmonic_minor", "dorian"],
    instrument_roles={
        "kick":        InstrumentRole(eq=kick_edm(punchy=False), comp=comp_kick_edm(), volume_db=-2.0,
                                      sends=[ReverbSend("room", -18.0)]),
        "snare":       InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-4.0,
                                      sends=[ReverbSend("plate", -10.0)]),
        "hats":        InstrumentRole(eq=hats(), volume_db=-10.0, pan=0.15,
                                      sends=[ReverbSend("room", -16.0)]),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-12.0, pan=-0.2,
                                      sends=[ReverbSend("plate", -12.0)]),
        "sub_bass":    InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-3.0),
        "growl_bass":  InstrumentRole(eq=mid_bass(), comp=comp_bass_edm(), volume_db=-4.0,
                                      sends=[ReverbSend("plate", -14.0)]),
        "lead_synth":  InstrumentRole(eq=lead_synth(), comp=comp_lead_synth(), volume_db=-5.0,
                                      sends=[ReverbSend("plate", -6.0), ReverbSend("hall", -12.0)]),
        "pluck_synth": InstrumentRole(eq=pluck_synth(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "pad":         InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-8.0,
                                      sends=[ReverbSend("hall", -4.0), ReverbSend("plate", -8.0)]),
        "piano":       InstrumentRole(eq=piano_modern(), volume_db=-5.0,
                                      sends=[ReverbSend("hall", -8.0), ReverbSend("plate", -10.0)]),
        "vocal_lead":  InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-3.0,
                                      sends=[ReverbSend("plate", -6.0), ReverbSend("hall", -10.0)]),
        "vocal_chop":  InstrumentRole(eq=vocal_chop(), volume_db=-6.0, pan=0.1,
                                      sends=[ReverbSend("plate", -5.0)]),
        "riser_fx":    InstrumentRole(eq=riser_fx(), volume_db=-8.0,
                                      sends=[ReverbSend("plate", -6.0)]),
        "impact_fx":   InstrumentRole(eq=impact_fx(), volume_db=-4.0),
    },
    aliases=default_aliases(["kick", "snare", "hats", "perc", "sub_bass", "growl_bass",
                              "lead_synth", "pluck_synth", "pad", "piano",
                              "vocal_lead", "vocal_chop", "riser_fx", "impact_fx"]),
    sidechain=[
        SidechainSpec(source="kick", target="pad",        amount=0.85, attack_ms=3,  release_ms=200),
        SidechainSpec(source="kick", target="sub_bass",   amount=0.75, attack_ms=2,  release_ms=150),
        SidechainSpec(source="kick", target="growl_bass", amount=0.60, attack_ms=3,  release_ms=120),
        SidechainSpec(source="kick", target="vocal_chop", amount=0.50, attack_ms=5,  release_ms=180),
        SidechainSpec(source="kick", target="piano",      amount=0.55, attack_ms=4,  release_ms=180),
    ],
    reverb_buses={
        "hall":  ReverbBus(room_size=0.80, dampening=0.30, wet_db=-6, lowpass_hz=14000, hipass_hz=150, width=1.1, color=(70,130,200)),
        "room":  ReverbBus(room_size=0.40, dampening=0.55, wet_db=-8, lowpass_hz=9000,  hipass_hz=200, width=0.8, color=(70,180,70)),
        "plate": ReverbBus(room_size=0.60, dampening=0.20, wet_db=-6, lowpass_hz=16000, hipass_hz=250, width=1.2, color=(200,70,180)),
    },
    mastering=MasteringChain(
        target_lufs=-8.0, true_peak_db=-1.0, stereo_width=1.15, limiter_character="transparent",
        low_shelf_db=1.0, low_shelf_freq=60, high_shelf_db=1.5, high_shelf_freq=12000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "verse", "build", "drop", "breakdown", "build2", "drop2", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# BIG ROOM — festival main-stage. Simple hook lead, massive kick,
# heavy sidechain on everything. -6 LUFS slammed. Punchy.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="big_room",
    family="edm",
    bpm_range=(126, 132),
    key_hints=["minor", "major"],
    instrument_roles={
        "kick":        InstrumentRole(eq=kick_edm(punchy=True), comp=comp_kick_edm(), volume_db=0.0),
        "snare":       InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-3.0,
                                      sends=[ReverbSend("plate", -10.0)]),
        "hats":        InstrumentRole(eq=hats(), volume_db=-10.0, pan=0.1),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-12.0, pan=-0.2),
        "sub_bass":    InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-3.0),
        "bass":        InstrumentRole(eq=mid_bass(), comp=comp_bass_edm(), volume_db=-4.0),
        "lead_synth":  InstrumentRole(eq=lead_synth(), comp=comp_lead_synth(), volume_db=-3.0,
                                      sends=[ReverbSend("plate", -10.0)]),
        "pluck_synth": InstrumentRole(eq=pluck_synth(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -10.0)]),
        "pad":         InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-9.0,
                                      sends=[ReverbSend("hall", -6.0)]),
        "chord_stab":  InstrumentRole(eq=chord_stab(), volume_db=-5.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "vocal_lead":  InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-3.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "riser_fx":    InstrumentRole(eq=riser_fx(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -4.0)]),
        "impact_fx":   InstrumentRole(eq=impact_fx(), volume_db=-2.0),
    },
    aliases=default_aliases(["kick", "snare", "hats", "perc", "sub_bass", "bass",
                              "lead_synth", "pluck_synth", "pad", "chord_stab",
                              "vocal_lead", "riser_fx", "impact_fx"]),
    sidechain=[
        SidechainSpec(source="kick", target="pad",         amount=0.90, attack_ms=2, release_ms=220),
        SidechainSpec(source="kick", target="sub_bass",    amount=0.85, attack_ms=2, release_ms=140),
        SidechainSpec(source="kick", target="bass",        amount=0.80, attack_ms=2, release_ms=160),
        SidechainSpec(source="kick", target="chord_stab",  amount=0.75, attack_ms=3, release_ms=180),
        SidechainSpec(source="kick", target="lead_synth",  amount=0.60, attack_ms=5, release_ms=200),
    ],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-6.0, true_peak_db=-0.8, stereo_width=1.1, limiter_character="aggressive",
        low_shelf_db=1.5, low_shelf_freq=70, high_shelf_db=1.0, high_shelf_freq=11000,
        bus_comp=comp_master_glue(),
    ),
    structure_hints=["intro", "build", "drop", "breakdown", "build2", "drop2", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# FUTURE BASS — pitched chord stabs, vocal chops, bright, heavy pump.
# -7 LUFS. High shelf lift for sparkle.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="future_bass",
    family="edm",
    bpm_range=(140, 160),  # 70-80 half-time
    key_hints=["major", "minor"],
    instrument_roles={
        "kick":        InstrumentRole(eq=kick_edm(punchy=True), comp=comp_kick_edm(), volume_db=-2.0),
        "snare":       InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-3.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "hats":        InstrumentRole(eq=hats(), volume_db=-9.0, pan=0.2),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-11.0, pan=-0.15),
        "sub_bass":    InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-3.0),
        "bass_808":    InstrumentRole(eq=bass_808(), comp=comp_bass_edm(), volume_db=-4.0),
        "chord_stab":  InstrumentRole(eq=chord_stab(), comp=comp_lead_synth(), volume_db=-4.0,
                                      sends=[ReverbSend("plate", -5.0), ReverbSend("hall", -10.0)]),
        "lead_synth":  InstrumentRole(eq=lead_synth(), comp=comp_lead_synth(), volume_db=-4.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "pad":         InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-8.0,
                                      sends=[ReverbSend("hall", -5.0)]),
        "vocal_lead":  InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-3.0,
                                      sends=[ReverbSend("plate", -6.0), ReverbSend("hall", -12.0)]),
        "vocal_chop":  InstrumentRole(eq=vocal_chop(), volume_db=-5.0, pan=0.15,
                                      sends=[ReverbSend("plate", -5.0)]),
        "pluck_synth": InstrumentRole(eq=pluck_synth(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "riser_fx":    InstrumentRole(eq=riser_fx(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -5.0)]),
        "impact_fx":   InstrumentRole(eq=impact_fx(), volume_db=-3.0),
    },
    aliases=default_aliases(["kick", "snare", "hats", "perc", "sub_bass", "bass_808",
                              "chord_stab", "lead_synth", "pad", "vocal_lead", "vocal_chop",
                              "pluck_synth", "riser_fx", "impact_fx"]),
    sidechain=[
        SidechainSpec(source="kick", target="chord_stab", amount=0.85, attack_ms=2, release_ms=200),
        SidechainSpec(source="kick", target="pad",        amount=0.85, attack_ms=2, release_ms=220),
        SidechainSpec(source="kick", target="sub_bass",   amount=0.70, attack_ms=2, release_ms=140),
        SidechainSpec(source="kick", target="bass_808",   amount=0.70, attack_ms=2, release_ms=160),
        SidechainSpec(source="kick", target="vocal_chop", amount=0.65, attack_ms=4, release_ms=190),
    ],
    reverb_buses={
        "hall":  ReverbBus(room_size=0.75, dampening=0.30, wet_db=-7, lowpass_hz=13000, hipass_hz=150, width=1.1, color=(70,130,200)),
        "room":  ReverbBus(room_size=0.40, dampening=0.50, wet_db=-8, lowpass_hz=10000, hipass_hz=200, width=0.8, color=(70,180,70)),
        "plate": ReverbBus(room_size=0.60, dampening=0.15, wet_db=-6, lowpass_hz=18000, hipass_hz=250, width=1.3, color=(200,70,180)),
    },
    mastering=MasteringChain(
        target_lufs=-7.0, true_peak_db=-1.0, stereo_width=1.2, limiter_character="punchy",
        low_shelf_db=0.5, low_shelf_freq=60, high_shelf_db=2.0, high_shelf_freq=12000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "verse", "build", "drop", "verse2", "build2", "drop2", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# FUTURE HOUSE — plucky supersaw bass, filtered sweeps, tight kick.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="future_house",
    family="edm",
    bpm_range=(124, 128),
    key_hints=["minor", "major"],
    instrument_roles={
        "kick":        InstrumentRole(eq=kick_edm(punchy=True), comp=comp_kick_edm(), volume_db=-2.0),
        "snare":       InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-4.0,
                                      sends=[ReverbSend("plate", -10.0)]),
        "hats":        InstrumentRole(eq=hats(), volume_db=-9.0, pan=0.2),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-11.0, pan=-0.2),
        "sub_bass":    InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-4.0),
        "bass":        InstrumentRole(eq=mid_bass(), comp=comp_bass_edm(), volume_db=-4.0),
        "pluck_synth": InstrumentRole(eq=pluck_synth(), comp=comp_lead_synth(), volume_db=-5.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "lead_synth":  InstrumentRole(eq=lead_synth(), comp=comp_lead_synth(), volume_db=-5.0,
                                      sends=[ReverbSend("plate", -10.0)]),
        "chord_stab":  InstrumentRole(eq=chord_stab(), volume_db=-5.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "pad":         InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-10.0,
                                      sends=[ReverbSend("hall", -8.0)]),
        "vocal_chop":  InstrumentRole(eq=vocal_chop(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -6.0)]),
        "riser_fx":    InstrumentRole(eq=riser_fx(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -6.0)]),
        "impact_fx":   InstrumentRole(eq=impact_fx(), volume_db=-4.0),
    },
    aliases=default_aliases(["kick", "snare", "hats", "perc", "sub_bass", "bass",
                              "pluck_synth", "lead_synth", "chord_stab", "pad", "vocal_chop",
                              "riser_fx", "impact_fx"]),
    sidechain=[
        SidechainSpec(source="kick", target="pad",         amount=0.80, attack_ms=2, release_ms=200),
        SidechainSpec(source="kick", target="sub_bass",    amount=0.70, attack_ms=2, release_ms=140),
        SidechainSpec(source="kick", target="bass",        amount=0.70, attack_ms=2, release_ms=150),
        SidechainSpec(source="kick", target="chord_stab",  amount=0.65, attack_ms=3, release_ms=170),
    ],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-7.0, true_peak_db=-1.0, stereo_width=1.1, limiter_character="punchy",
        low_shelf_db=1.0, low_shelf_freq=70, high_shelf_db=1.0, high_shelf_freq=11000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "verse", "build", "drop", "breakdown", "build2", "drop2", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# DEEP HOUSE — warm, laid-back, jazzy chords. Dynamics preserved.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="deep_house",
    family="edm",
    bpm_range=(118, 124),
    key_hints=["minor", "dorian", "major"],
    instrument_roles={
        "kick":        InstrumentRole(eq=kick_edm(punchy=False), comp=comp_kick_edm(), volume_db=-3.0),
        "snare":       InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-5.0,
                                      sends=[ReverbSend("room", -10.0)]),
        "hats":        InstrumentRole(eq=hats(), volume_db=-9.0, pan=0.15),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-10.0, pan=-0.2),
        "sub_bass":    InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-5.0),
        "bass":        InstrumentRole(eq=mid_bass(), comp=comp_bass_edm(), volume_db=-5.0),
        "chord_stab":  InstrumentRole(eq=chord_stab(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -10.0)]),
        "pad":         InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-10.0,
                                      sends=[ReverbSend("hall", -7.0)]),
        "piano":       InstrumentRole(eq=piano_modern(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -10.0), ReverbSend("hall", -12.0)]),
        "pluck_synth": InstrumentRole(eq=pluck_synth(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -10.0)]),
        "vocal_lead":  InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-4.0,
                                      sends=[ReverbSend("plate", -8.0), ReverbSend("hall", -12.0)]),
        "vocal_chop":  InstrumentRole(eq=vocal_chop(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -7.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "perc", "sub_bass", "bass",
                              "chord_stab", "pad", "piano", "pluck_synth",
                              "vocal_lead", "vocal_chop"]),
    sidechain=[
        SidechainSpec(source="kick", target="pad",        amount=0.45, attack_ms=10, release_ms=200),
        SidechainSpec(source="kick", target="sub_bass",   amount=0.35, attack_ms=5,  release_ms=150),
    ],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-10.0, true_peak_db=-1.0, stereo_width=1.05, limiter_character="warm",
        low_shelf_db=0.5, low_shelf_freq=80, high_shelf_db=0.5, high_shelf_freq=10000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "groove", "breakdown", "drop", "breakdown2", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# TECH HOUSE — driving, minimal, groove-focused. Drier mix.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="tech_house",
    family="edm",
    bpm_range=(124, 128),
    key_hints=["minor"],
    instrument_roles={
        "kick":        InstrumentRole(eq=kick_edm(punchy=True), comp=comp_kick_edm(), volume_db=-2.0),
        "snare":       InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-4.0),
        "clap":        InstrumentRole(eq=snare_edm(), volume_db=-4.0),
        "hats":        InstrumentRole(eq=hats(), volume_db=-8.0, pan=0.15),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-9.0, pan=-0.2),
        "sub_bass":    InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-4.0),
        "bass":        InstrumentRole(eq=mid_bass(), comp=comp_bass_edm(), volume_db=-4.0),
        "lead_synth":  InstrumentRole(eq=lead_synth(), comp=comp_lead_synth(), volume_db=-6.0),
        "chord_stab":  InstrumentRole(eq=chord_stab(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -12.0)]),
        "vocal_chop":  InstrumentRole(eq=vocal_chop(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -10.0)]),
    },
    aliases=default_aliases(["kick", "snare", "clap", "hats", "perc", "sub_bass", "bass",
                              "lead_synth", "chord_stab", "vocal_chop"]),
    sidechain=[
        SidechainSpec(source="kick", target="sub_bass",   amount=0.60, attack_ms=2, release_ms=130),
        SidechainSpec(source="kick", target="bass",       amount=0.60, attack_ms=2, release_ms=150),
    ],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-8.0, true_peak_db=-1.0, stereo_width=1.0, limiter_character="punchy",
        low_shelf_db=1.0, low_shelf_freq=70, high_shelf_db=0.5, high_shelf_freq=11000,
        bus_comp=comp_master_glue(),
    ),
    structure_hints=["intro", "groove", "breakdown", "drop", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# PROGRESSIVE HOUSE — long builds, emotional, uplifting.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="progressive_house",
    family="edm",
    bpm_range=(126, 130),
    key_hints=["minor", "major"],
    instrument_roles={
        "kick":        InstrumentRole(eq=kick_edm(punchy=True), comp=comp_kick_edm(), volume_db=-2.0),
        "snare":       InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-4.0,
                                      sends=[ReverbSend("plate", -9.0)]),
        "hats":        InstrumentRole(eq=hats(), volume_db=-9.0, pan=0.2),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-11.0, pan=-0.2),
        "sub_bass":    InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-4.0),
        "bass":        InstrumentRole(eq=mid_bass(), comp=comp_bass_edm(), volume_db=-5.0),
        "lead_synth":  InstrumentRole(eq=lead_synth(), comp=comp_lead_synth(), volume_db=-4.0,
                                      sends=[ReverbSend("plate", -8.0), ReverbSend("hall", -12.0)]),
        "pluck_synth": InstrumentRole(eq=pluck_synth(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "pad":         InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-8.0,
                                      sends=[ReverbSend("hall", -5.0)]),
        "piano":       InstrumentRole(eq=piano_modern(), volume_db=-6.0,
                                      sends=[ReverbSend("hall", -8.0)]),
        "vocal_lead":  InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-4.0,
                                      sends=[ReverbSend("plate", -8.0), ReverbSend("hall", -12.0)]),
        "vocal_chop":  InstrumentRole(eq=vocal_chop(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -6.0)]),
        "riser_fx":    InstrumentRole(eq=riser_fx(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -5.0)]),
        "impact_fx":   InstrumentRole(eq=impact_fx(), volume_db=-3.0),
    },
    aliases=default_aliases(["kick", "snare", "hats", "perc", "sub_bass", "bass",
                              "lead_synth", "pluck_synth", "pad", "piano",
                              "vocal_lead", "vocal_chop", "riser_fx", "impact_fx"]),
    sidechain=[
        SidechainSpec(source="kick", target="pad",        amount=0.80, attack_ms=3, release_ms=220),
        SidechainSpec(source="kick", target="sub_bass",   amount=0.65, attack_ms=2, release_ms=140),
        SidechainSpec(source="kick", target="bass",       amount=0.65, attack_ms=2, release_ms=160),
        SidechainSpec(source="kick", target="lead_synth", amount=0.50, attack_ms=5, release_ms=200),
    ],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-7.0, true_peak_db=-1.0, stereo_width=1.15, limiter_character="transparent",
        low_shelf_db=1.0, low_shelf_freq=70, high_shelf_db=1.5, high_shelf_freq=11000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "build", "drop", "breakdown", "build2", "drop2", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# DUBSTEP — aggressive, 140bpm half-time, no sidechain on drop.
# Huge wubs. Weighty kick. -6 LUFS slammed.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="dubstep",
    family="edm",
    bpm_range=(138, 142),  # 69-71 half-time
    key_hints=["minor", "phrygian", "locrian"],
    instrument_roles={
        "kick":        InstrumentRole(eq=kick_edm(punchy=False), comp=comp_kick_edm(), volume_db=-1.0),
        "snare":       InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-2.0,
                                      sends=[ReverbSend("plate", -6.0)]),
        "hats":        InstrumentRole(eq=hats(), volume_db=-10.0, pan=0.15),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-11.0, pan=-0.2),
        "sub_bass":    InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-2.0),
        "growl_bass":  InstrumentRole(eq=mid_bass(), comp=comp_bass_edm(), volume_db=-3.0),
        "reese_bass":  InstrumentRole(eq=mid_bass(), comp=comp_bass_edm(), volume_db=-4.0),
        "lead_synth":  InstrumentRole(eq=lead_synth(), comp=comp_lead_synth(), volume_db=-5.0,
                                      sends=[ReverbSend("plate", -10.0)]),
        "pad":         InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-10.0,
                                      sends=[ReverbSend("hall", -8.0)]),
        "vocal_chop":  InstrumentRole(eq=vocal_chop(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -6.0)]),
        "riser_fx":    InstrumentRole(eq=riser_fx(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -4.0)]),
        "impact_fx":   InstrumentRole(eq=impact_fx(), volume_db=-2.0),
    },
    aliases=default_aliases(["kick", "snare", "hats", "perc", "sub_bass", "growl_bass",
                              "reese_bass", "lead_synth", "pad", "vocal_chop",
                              "riser_fx", "impact_fx"]),
    sidechain=[
        # Only intro/breakdown pads — drop has no sidechain, bass takes the space
        SidechainSpec(source="kick", target="pad",        amount=0.60, attack_ms=5,  release_ms=200),
    ],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-6.0, true_peak_db=-0.8, stereo_width=1.05, limiter_character="aggressive",
        low_shelf_db=1.5, low_shelf_freq=60, high_shelf_db=1.0, high_shelf_freq=10000,
        bus_comp=comp_master_glue(),
    ),
    structure_hints=["intro", "build", "drop", "breakdown", "build2", "drop2", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# TRAP — 808s, rolled hats, pitch-bent sub. -7 LUFS.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="trap",
    family="edm",
    bpm_range=(140, 160),  # half-time feel 70-80
    key_hints=["minor", "phrygian", "harmonic_minor"],
    instrument_roles={
        "kick":       InstrumentRole(eq=kick_edm(punchy=True), comp=comp_kick_edm(), volume_db=-3.0),
        "snare":      InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-2.0,
                                     sends=[ReverbSend("plate", -6.0)]),
        "clap":       InstrumentRole(eq=snare_edm(), volume_db=-3.0,
                                     sends=[ReverbSend("plate", -7.0)]),
        "hats":       InstrumentRole(eq=hats(), volume_db=-7.0, pan=0.15),
        "open_hat":   InstrumentRole(eq=hats(), volume_db=-8.0, pan=-0.15),
        "perc":       InstrumentRole(eq=perc_bright(), volume_db=-10.0),
        "bass_808":   InstrumentRole(eq=bass_808(), comp=comp_bass_edm(), volume_db=-1.0),
        "sub_bass":   InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-3.0),
        "lead_synth": InstrumentRole(eq=lead_synth(), comp=comp_lead_synth(), volume_db=-6.0,
                                     sends=[ReverbSend("plate", -8.0)]),
        "pluck_synth":InstrumentRole(eq=pluck_synth(), volume_db=-7.0,
                                     sends=[ReverbSend("plate", -8.0)]),
        "pad":        InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-10.0,
                                     sends=[ReverbSend("hall", -8.0)]),
        "vocal_lead": InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-3.0,
                                     sends=[ReverbSend("plate", -8.0), ReverbSend("hall", -14.0)]),
        "vocal_chop": InstrumentRole(eq=vocal_chop(), volume_db=-7.0,
                                     sends=[ReverbSend("plate", -6.0)]),
    },
    aliases=default_aliases(["kick", "snare", "clap", "hats", "open_hat", "perc",
                              "bass_808", "sub_bass", "lead_synth", "pluck_synth", "pad",
                              "vocal_lead", "vocal_chop"]),
    sidechain=[
        SidechainSpec(source="kick", target="bass_808",  amount=0.70, attack_ms=2, release_ms=120),
        SidechainSpec(source="kick", target="sub_bass",  amount=0.60, attack_ms=2, release_ms=120),
        SidechainSpec(source="kick", target="pad",       amount=0.45, attack_ms=8, release_ms=180),
    ],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-7.0, true_peak_db=-1.0, stereo_width=1.0, limiter_character="punchy",
        low_shelf_db=1.5, low_shelf_freq=50, high_shelf_db=1.5, high_shelf_freq=11000,
        bus_comp=comp_master_glue(),
    ),
    structure_hints=["intro", "verse", "hook", "verse2", "hook2", "bridge", "hook3", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# DRUM AND BASS — 170bpm, reese bass, breakbeats.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="drum_and_bass",
    family="edm",
    bpm_range=(170, 180),
    key_hints=["minor", "dorian"],
    instrument_roles={
        "kick":        InstrumentRole(eq=kick_edm(punchy=True), comp=comp_kick_edm(), volume_db=-2.0),
        "snare":       InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-1.0,
                                      sends=[ReverbSend("plate", -7.0)]),
        "hats":        InstrumentRole(eq=hats(), volume_db=-8.0, pan=0.15),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-10.0, pan=-0.2),
        "sub_bass":    InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-2.0),
        "reese_bass":  InstrumentRole(eq=mid_bass(), comp=comp_bass_edm(), volume_db=-3.0),
        "lead_synth":  InstrumentRole(eq=lead_synth(), comp=comp_lead_synth(), volume_db=-5.0,
                                      sends=[ReverbSend("plate", -10.0)]),
        "pad":         InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-10.0,
                                      sends=[ReverbSend("hall", -8.0)]),
        "vocal_chop":  InstrumentRole(eq=vocal_chop(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -7.0)]),
        "riser_fx":    InstrumentRole(eq=riser_fx(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -5.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "perc", "sub_bass", "reese_bass",
                              "lead_synth", "pad", "vocal_chop", "riser_fx"]),
    sidechain=[
        SidechainSpec(source="kick", target="sub_bass",   amount=0.55, attack_ms=2, release_ms=100),
        SidechainSpec(source="kick", target="reese_bass", amount=0.50, attack_ms=2, release_ms=100),
        SidechainSpec(source="kick", target="pad",        amount=0.60, attack_ms=5, release_ms=180),
    ],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-6.0, true_peak_db=-1.0, stereo_width=1.1, limiter_character="aggressive",
        low_shelf_db=1.5, low_shelf_freq=60, high_shelf_db=1.0, high_shelf_freq=11000,
        bus_comp=comp_master_glue(),
    ),
    structure_hints=["intro", "breakdown", "drop", "breakdown2", "drop2", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# TRANCE — uplifting leads, long risers, plate reverb.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="trance",
    family="edm",
    bpm_range=(132, 140),
    key_hints=["minor", "major"],
    instrument_roles={
        "kick":        InstrumentRole(eq=kick_edm(punchy=True), comp=comp_kick_edm(), volume_db=-2.0),
        "snare":       InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-4.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "hats":        InstrumentRole(eq=hats(), volume_db=-8.0, pan=0.15),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-11.0, pan=-0.2),
        "sub_bass":    InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-3.0),
        "bass":        InstrumentRole(eq=mid_bass(), comp=comp_bass_edm(), volume_db=-4.0),
        "lead_synth":  InstrumentRole(eq=lead_synth(), comp=comp_lead_synth(), volume_db=-3.0,
                                      sends=[ReverbSend("plate", -6.0), ReverbSend("hall", -10.0)]),
        "pluck_synth": InstrumentRole(eq=pluck_synth(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -7.0)]),
        "pad":         InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-7.0,
                                      sends=[ReverbSend("hall", -4.0)]),
        "riser_fx":    InstrumentRole(eq=riser_fx(), volume_db=-5.0,
                                      sends=[ReverbSend("plate", -4.0)]),
        "impact_fx":   InstrumentRole(eq=impact_fx(), volume_db=-3.0),
    },
    aliases=default_aliases(["kick", "snare", "hats", "perc", "sub_bass", "bass",
                              "lead_synth", "pluck_synth", "pad", "riser_fx", "impact_fx"]),
    sidechain=[
        SidechainSpec(source="kick", target="pad",         amount=0.85, attack_ms=2, release_ms=250),
        SidechainSpec(source="kick", target="sub_bass",    amount=0.70, attack_ms=2, release_ms=140),
        SidechainSpec(source="kick", target="bass",        amount=0.70, attack_ms=2, release_ms=150),
        SidechainSpec(source="kick", target="pluck_synth", amount=0.50, attack_ms=5, release_ms=200),
    ],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-7.0, true_peak_db=-1.0, stereo_width=1.2, limiter_character="transparent",
        low_shelf_db=0.5, low_shelf_freq=70, high_shelf_db=2.0, high_shelf_freq=12000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "build", "drop", "breakdown", "build2", "drop2", "outro"],
))
