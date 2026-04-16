"""Electronic adjacent style profiles — synthwave, lofi, ambient, hiphop."""

from reaper_mcp.mix_engine.profiles_v2 import (
    StyleProfile, InstrumentRole, SidechainSpec, MasteringChain, ReverbBus, ReverbSend,
    register_profile, DEFAULT_REVERB_BUSES,
)
from reaper_mcp.mix_engine.catalog._shared import (
    kick_edm, snare_edm, hats, perc_bright,
    sub_bass, bass_808, mid_bass, bass_guitar,
    lead_synth, pluck_synth, pad, chord_stab, piano_modern,
    vocal_lead, vocal_chop, riser_fx, impact_fx,
    comp_kick_edm, comp_snare_edm, comp_bass_edm, comp_vocal, comp_lead_synth,
    comp_pad, comp_master_transparent, comp_master_glue,
    default_aliases,
)


# ═════════════════════════════════════════════════════════════════
# SYNTHWAVE — 80s retrowave, gated snare, wide stereo leads.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="synthwave",
    family="electronic",
    bpm_range=(85, 115),
    key_hints=["minor", "major"],
    instrument_roles={
        "kick":        InstrumentRole(eq=kick_edm(punchy=True), comp=comp_kick_edm(), volume_db=-2.0),
        "snare":       InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-3.0,
                                      sends=[ReverbSend("plate", -5.0), ReverbSend("hall", -9.0)]),
        "hats":        InstrumentRole(eq=hats(), volume_db=-10.0, pan=0.2),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-11.0, pan=-0.15),
        "toms":        InstrumentRole(eq=perc_bright(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "sub_bass":    InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-4.0),
        "bass":        InstrumentRole(eq=mid_bass(), comp=comp_bass_edm(), volume_db=-4.0),
        "lead_synth":  InstrumentRole(eq=lead_synth(), comp=comp_lead_synth(), volume_db=-4.0,
                                      sends=[ReverbSend("plate", -6.0), ReverbSend("hall", -10.0)]),
        "pluck_synth": InstrumentRole(eq=pluck_synth(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "pad":         InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-8.0,
                                      sends=[ReverbSend("hall", -5.0)]),
        "chord_stab":  InstrumentRole(eq=chord_stab(), volume_db=-5.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "vocal_lead":  InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-4.0,
                                      sends=[ReverbSend("plate", -6.0), ReverbSend("hall", -10.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "perc", "toms", "sub_bass", "bass",
                              "lead_synth", "pluck_synth", "pad", "chord_stab", "vocal_lead"]),
    sidechain=[
        SidechainSpec(source="kick", target="pad",        amount=0.55, attack_ms=5, release_ms=180),
        SidechainSpec(source="kick", target="sub_bass",   amount=0.45, attack_ms=3, release_ms=140),
    ],
    reverb_buses={
        "hall":  ReverbBus(room_size=0.85, dampening=0.30, wet_db=-5, lowpass_hz=13000, hipass_hz=150, width=1.2, color=(70,130,200)),
        "room":  ReverbBus(room_size=0.45, dampening=0.50, wet_db=-7, lowpass_hz=10000, hipass_hz=180, width=0.8, color=(70,180,70)),
        "plate": ReverbBus(room_size=0.70, dampening=0.15, wet_db=-5, lowpass_hz=17000, hipass_hz=250, width=1.3, color=(200,70,180)),
    },
    mastering=MasteringChain(
        target_lufs=-10.0, true_peak_db=-1.0, stereo_width=1.2, limiter_character="warm",
        low_shelf_db=0.5, low_shelf_freq=80, high_shelf_db=1.5, high_shelf_freq=12000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "verse", "chorus", "verse2", "chorus2", "bridge", "chorus3", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# LOFI HIP HOP — dusty, compressed, vinyl-warm. Tape-style mastering.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="lofi",
    family="electronic",
    bpm_range=(70, 90),
    key_hints=["minor", "dorian"],
    instrument_roles={
        "kick":        InstrumentRole(eq=kick_edm(punchy=False), comp=comp_kick_edm(), volume_db=-4.0),
        "snare":       InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-5.0,
                                      sends=[ReverbSend("room", -8.0)]),
        "hats":        InstrumentRole(eq=hats(), volume_db=-11.0, pan=0.15),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-12.0),
        "bass":        InstrumentRole(eq=mid_bass(), comp=comp_bass_edm(), volume_db=-4.0),
        "sub_bass":    InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-5.0),
        "piano":       InstrumentRole(eq=piano_modern(), volume_db=-5.0,
                                      sends=[ReverbSend("room", -8.0), ReverbSend("plate", -10.0)]),
        "chord_stab":  InstrumentRole(eq=chord_stab(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -9.0)]),
        "pluck_synth": InstrumentRole(eq=pluck_synth(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -10.0)]),
        "pad":         InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-10.0,
                                      sends=[ReverbSend("hall", -8.0)]),
        "vocal_chop":  InstrumentRole(eq=vocal_chop(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -6.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "perc", "bass", "sub_bass",
                              "piano", "chord_stab", "pluck_synth", "pad", "vocal_chop"]),
    sidechain=[],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-14.0, true_peak_db=-1.0, stereo_width=1.0, limiter_character="warm",
        low_shelf_db=1.0, low_shelf_freq=100, high_shelf_db=-1.0, high_shelf_freq=8000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "loop", "break", "loop2", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# AMBIENT — minimal, texture-focused, huge reverb, wide stereo.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="ambient",
    family="electronic",
    bpm_range=(50, 90),
    key_hints=["major", "minor", "lydian", "dorian"],
    instrument_roles={
        "pad":         InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-4.0,
                                      sends=[ReverbSend("hall", -3.0)]),
        "piano":       InstrumentRole(eq=piano_modern(), volume_db=-6.0,
                                      sends=[ReverbSend("hall", -5.0), ReverbSend("plate", -8.0)]),
        "pluck_synth": InstrumentRole(eq=pluck_synth(), volume_db=-7.0,
                                      sends=[ReverbSend("hall", -5.0), ReverbSend("plate", -8.0)]),
        "sub_bass":    InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-6.0),
        "vocal_chop":  InstrumentRole(eq=vocal_chop(), volume_db=-8.0,
                                      sends=[ReverbSend("hall", -4.0), ReverbSend("plate", -8.0)]),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-14.0,
                                      sends=[ReverbSend("hall", -6.0)]),
        "riser_fx":    InstrumentRole(eq=riser_fx(), volume_db=-8.0,
                                      sends=[ReverbSend("hall", -4.0), ReverbSend("plate", -6.0)]),
    },
    aliases=default_aliases(["pad", "piano", "pluck_synth", "sub_bass", "vocal_chop",
                              "perc", "riser_fx"]),
    sidechain=[],
    reverb_buses={
        "hall":  ReverbBus(room_size=0.95, dampening=0.20, wet_db=-3, lowpass_hz=15000, hipass_hz=80, width=1.4, color=(70,130,200)),
        "room":  ReverbBus(room_size=0.60, dampening=0.35, wet_db=-6, lowpass_hz=12000, hipass_hz=150, width=1.0, color=(70,180,70)),
        "plate": ReverbBus(room_size=0.80, dampening=0.15, wet_db=-4, lowpass_hz=18000, hipass_hz=250, width=1.4, color=(200,70,180)),
    },
    mastering=MasteringChain(
        target_lufs=-16.0, true_peak_db=-1.0, stereo_width=1.3, limiter_character="transparent",
        low_shelf_db=0.5, low_shelf_freq=80, high_shelf_db=1.5, high_shelf_freq=12000,
        bus_comp=None,  # no bus comp for ambient — dynamics are the point
    ),
    structure_hints=["intro", "evolve", "peak", "decay", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# HIP HOP — 808-driven, punchy snare, sub-heavy, vocal forward.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="hiphop",
    family="electronic",
    bpm_range=(70, 105),
    key_hints=["minor", "phrygian", "dorian"],
    instrument_roles={
        "kick":        InstrumentRole(eq=kick_edm(punchy=True), comp=comp_kick_edm(), volume_db=-2.0),
        "snare":       InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-2.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "clap":        InstrumentRole(eq=snare_edm(), volume_db=-3.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "hats":        InstrumentRole(eq=hats(), volume_db=-8.0, pan=0.15),
        "open_hat":    InstrumentRole(eq=hats(), volume_db=-9.0, pan=-0.15),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-10.0),
        "bass_808":    InstrumentRole(eq=bass_808(), comp=comp_bass_edm(), volume_db=-1.0),
        "sub_bass":    InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-3.0),
        "lead_synth":  InstrumentRole(eq=lead_synth(), comp=comp_lead_synth(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -10.0)]),
        "pluck_synth": InstrumentRole(eq=pluck_synth(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -9.0)]),
        "piano":       InstrumentRole(eq=piano_modern(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -9.0)]),
        "pad":         InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-10.0,
                                      sends=[ReverbSend("hall", -8.0)]),
        "chord_stab":  InstrumentRole(eq=chord_stab(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -9.0)]),
        "vocal_lead":  InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-2.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "vocal_backup":InstrumentRole(eq=vocal_chop(), comp=comp_vocal(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -8.0)]),
    },
    aliases=default_aliases(["kick", "snare", "clap", "hats", "open_hat", "perc",
                              "bass_808", "sub_bass", "lead_synth", "pluck_synth", "piano",
                              "pad", "chord_stab", "vocal_lead", "vocal_backup"]),
    sidechain=[
        SidechainSpec(source="kick", target="bass_808",  amount=0.70, attack_ms=2, release_ms=120),
        SidechainSpec(source="kick", target="sub_bass",  amount=0.60, attack_ms=2, release_ms=120),
    ],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-8.0, true_peak_db=-1.0, stereo_width=1.05, limiter_character="punchy",
        low_shelf_db=2.0, low_shelf_freq=50, high_shelf_db=1.0, high_shelf_freq=11000,
        bus_comp=comp_master_glue(),
    ),
    structure_hints=["intro", "verse", "hook", "verse2", "hook2", "bridge", "hook3", "outro"],
))
