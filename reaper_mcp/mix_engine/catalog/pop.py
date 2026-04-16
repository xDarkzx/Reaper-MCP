"""Pop style profiles — 4 subgenres: modern, dance, indie, R&B."""

from reaper_mcp.mix_engine.profiles_v2 import (
    StyleProfile, InstrumentRole, SidechainSpec, MasteringChain, ReverbSend,
    register_profile, DEFAULT_REVERB_BUSES,
)
from reaper_mcp.mix_engine.catalog._shared import (
    kick_edm, snare_edm, hats, perc_bright,
    sub_bass, mid_bass, bass_guitar, bass_808,
    lead_synth, pluck_synth, pad, chord_stab, piano_modern,
    vocal_lead, vocal_backup, vocal_chop,
    clean_guitar, rhythm_guitar,
    comp_kick_edm, comp_snare_edm, comp_bass_edm, comp_vocal, comp_lead_synth,
    comp_pad, comp_master_transparent, comp_master_glue,
    default_aliases,
)


# ═════════════════════════════════════════════════════════════════
# MODERN POP — vocal-first, tight production, light pump on pads.
# -9 LUFS. Plate reverb on vocal. Stereo width 1.1.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="modern_pop",
    family="pop",
    bpm_range=(95, 120),
    key_hints=["major", "minor"],
    instrument_roles={
        "kick":          InstrumentRole(eq=kick_edm(punchy=True), comp=comp_kick_edm(), volume_db=-2.0),
        "snare":         InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-3.0,
                                         sends=[ReverbSend("plate", -10.0)]),
        "clap":          InstrumentRole(eq=snare_edm(), volume_db=-5.0,
                                         sends=[ReverbSend("plate", -10.0)]),
        "hats":          InstrumentRole(eq=hats(), volume_db=-10.0, pan=0.2),
        "perc":          InstrumentRole(eq=perc_bright(), volume_db=-12.0),
        "sub_bass":      InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-4.0),
        "bass_808":      InstrumentRole(eq=bass_808(), comp=comp_bass_edm(), volume_db=-4.0),
        "bass_guitar":   InstrumentRole(eq=bass_guitar(), comp=comp_bass_edm(), volume_db=-4.0),
        "pluck_synth":   InstrumentRole(eq=pluck_synth(), volume_db=-7.0,
                                         sends=[ReverbSend("plate", -10.0)]),
        "lead_synth":    InstrumentRole(eq=lead_synth(), comp=comp_lead_synth(), volume_db=-5.0,
                                         sends=[ReverbSend("plate", -10.0)]),
        "pad":           InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-9.0,
                                         sends=[ReverbSend("hall", -8.0)]),
        "chord_stab":    InstrumentRole(eq=chord_stab(), volume_db=-6.0,
                                         sends=[ReverbSend("plate", -10.0)]),
        "piano":         InstrumentRole(eq=piano_modern(), volume_db=-5.0,
                                         sends=[ReverbSend("hall", -10.0), ReverbSend("plate", -12.0)]),
        "clean_guitar":  InstrumentRole(eq=clean_guitar(), volume_db=-7.0, pan=0.2,
                                         sends=[ReverbSend("plate", -10.0)]),
        "vocal_lead":    InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-2.0,
                                         sends=[ReverbSend("plate", -8.0), ReverbSend("hall", -14.0)]),
        "vocal_backup":  InstrumentRole(eq=vocal_backup(), comp=comp_vocal(), volume_db=-7.0,
                                         sends=[ReverbSend("plate", -8.0)]),
        "vocal_chop":    InstrumentRole(eq=vocal_chop(), volume_db=-7.0,
                                         sends=[ReverbSend("plate", -6.0)]),
    },
    aliases=default_aliases(["kick", "snare", "clap", "hats", "perc",
                              "sub_bass", "bass_808", "bass_guitar",
                              "pluck_synth", "lead_synth", "pad", "chord_stab", "piano",
                              "clean_guitar", "vocal_lead", "vocal_backup", "vocal_chop"]),
    sidechain=[
        SidechainSpec(source="kick", target="pad",        amount=0.55, attack_ms=5, release_ms=180),
        SidechainSpec(source="kick", target="sub_bass",   amount=0.50, attack_ms=3, release_ms=140),
        SidechainSpec(source="kick", target="bass_808",   amount=0.45, attack_ms=3, release_ms=150),
    ],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-9.0, true_peak_db=-1.0, stereo_width=1.1, limiter_character="transparent",
        low_shelf_db=0.5, low_shelf_freq=80, high_shelf_db=1.5, high_shelf_freq=12000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "verse", "pre_chorus", "chorus", "verse2", "pre_chorus2", "chorus2",
                      "bridge", "chorus3", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# DANCE POP — club-ready, kick/pad sidechain, bright lead synth.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="dance_pop",
    family="pop",
    bpm_range=(118, 128),
    key_hints=["minor", "major"],
    instrument_roles={
        "kick":        InstrumentRole(eq=kick_edm(punchy=True), comp=comp_kick_edm(), volume_db=-2.0),
        "snare":       InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-3.0,
                                      sends=[ReverbSend("plate", -9.0)]),
        "clap":        InstrumentRole(eq=snare_edm(), volume_db=-4.0,
                                      sends=[ReverbSend("plate", -10.0)]),
        "hats":        InstrumentRole(eq=hats(), volume_db=-9.0, pan=0.2),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-11.0),
        "sub_bass":    InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-4.0),
        "bass":        InstrumentRole(eq=mid_bass(), comp=comp_bass_edm(), volume_db=-4.0),
        "lead_synth":  InstrumentRole(eq=lead_synth(), comp=comp_lead_synth(), volume_db=-4.0,
                                      sends=[ReverbSend("plate", -9.0)]),
        "pluck_synth": InstrumentRole(eq=pluck_synth(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -10.0)]),
        "pad":         InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-9.0,
                                      sends=[ReverbSend("hall", -8.0)]),
        "chord_stab":  InstrumentRole(eq=chord_stab(), volume_db=-5.0,
                                      sends=[ReverbSend("plate", -9.0)]),
        "vocal_lead":  InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-3.0,
                                      sends=[ReverbSend("plate", -8.0), ReverbSend("hall", -14.0)]),
        "vocal_backup":InstrumentRole(eq=vocal_backup(), comp=comp_vocal(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "vocal_chop":  InstrumentRole(eq=vocal_chop(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -7.0)]),
    },
    aliases=default_aliases(["kick", "snare", "clap", "hats", "perc", "sub_bass", "bass",
                              "lead_synth", "pluck_synth", "pad", "chord_stab",
                              "vocal_lead", "vocal_backup", "vocal_chop"]),
    sidechain=[
        SidechainSpec(source="kick", target="pad",         amount=0.75, attack_ms=3, release_ms=200),
        SidechainSpec(source="kick", target="sub_bass",    amount=0.60, attack_ms=2, release_ms=140),
        SidechainSpec(source="kick", target="bass",        amount=0.60, attack_ms=2, release_ms=150),
        SidechainSpec(source="kick", target="chord_stab",  amount=0.55, attack_ms=4, release_ms=180),
    ],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-8.0, true_peak_db=-1.0, stereo_width=1.15, limiter_character="punchy",
        low_shelf_db=1.0, low_shelf_freq=70, high_shelf_db=1.5, high_shelf_freq=12000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "verse", "pre_chorus", "chorus", "verse2", "chorus2", "bridge", "chorus3", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# INDIE POP — lo-fi warmth, reverby vocal, less compression.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="indie_pop",
    family="pop",
    bpm_range=(90, 130),
    key_hints=["major", "minor", "dorian"],
    instrument_roles={
        "kick":        InstrumentRole(eq=kick_edm(punchy=False), comp=comp_kick_edm(), volume_db=-3.0),
        "snare":       InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-4.0,
                                      sends=[ReverbSend("room", -8.0), ReverbSend("plate", -12.0)]),
        "hats":        InstrumentRole(eq=hats(), volume_db=-10.0, pan=0.2,
                                      sends=[ReverbSend("room", -14.0)]),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-11.0, pan=-0.2),
        "bass_guitar": InstrumentRole(eq=bass_guitar(), comp=comp_bass_edm(), volume_db=-4.0),
        "clean_guitar":InstrumentRole(eq=clean_guitar(), volume_db=-5.0, pan=0.3,
                                      sends=[ReverbSend("plate", -8.0), ReverbSend("hall", -12.0)]),
        "piano":       InstrumentRole(eq=piano_modern(), volume_db=-6.0,
                                      sends=[ReverbSend("hall", -8.0)]),
        "pad":         InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-9.0,
                                      sends=[ReverbSend("hall", -6.0)]),
        "vocal_lead":  InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-3.0,
                                      sends=[ReverbSend("plate", -6.0), ReverbSend("hall", -10.0)]),
        "vocal_backup":InstrumentRole(eq=vocal_backup(), comp=comp_vocal(), volume_db=-8.0,
                                      sends=[ReverbSend("plate", -7.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "perc", "bass_guitar", "clean_guitar",
                              "piano", "pad", "vocal_lead", "vocal_backup"]),
    sidechain=[],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-11.0, true_peak_db=-1.0, stereo_width=1.1, limiter_character="warm",
        low_shelf_db=0.5, low_shelf_freq=80, high_shelf_db=1.0, high_shelf_freq=11000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "verse", "chorus", "verse2", "chorus2", "bridge", "chorus3", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# R&B POP — smooth, sub-heavy, intimate vocal, 808s.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="rnb_pop",
    family="pop",
    bpm_range=(70, 100),
    key_hints=["minor", "dorian", "major"],
    instrument_roles={
        "kick":        InstrumentRole(eq=kick_edm(punchy=False), comp=comp_kick_edm(), volume_db=-3.0),
        "snare":       InstrumentRole(eq=snare_edm(), comp=comp_snare_edm(), volume_db=-4.0,
                                      sends=[ReverbSend("plate", -9.0)]),
        "clap":        InstrumentRole(eq=snare_edm(), volume_db=-5.0,
                                      sends=[ReverbSend("plate", -9.0)]),
        "hats":        InstrumentRole(eq=hats(), volume_db=-9.0, pan=0.15),
        "perc":        InstrumentRole(eq=perc_bright(), volume_db=-11.0, pan=-0.2),
        "sub_bass":    InstrumentRole(eq=sub_bass(), comp=comp_bass_edm(), volume_db=-3.0),
        "bass_808":    InstrumentRole(eq=bass_808(), comp=comp_bass_edm(), volume_db=-3.0),
        "pluck_synth": InstrumentRole(eq=pluck_synth(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -10.0)]),
        "pad":         InstrumentRole(eq=pad(), comp=comp_pad(), volume_db=-9.0,
                                      sends=[ReverbSend("hall", -7.0)]),
        "chord_stab":  InstrumentRole(eq=chord_stab(), volume_db=-6.0,
                                      sends=[ReverbSend("plate", -9.0)]),
        "piano":       InstrumentRole(eq=piano_modern(), volume_db=-5.0,
                                      sends=[ReverbSend("plate", -9.0), ReverbSend("hall", -12.0)]),
        "vocal_lead":  InstrumentRole(eq=vocal_lead(), comp=comp_vocal(), volume_db=-2.0,
                                      sends=[ReverbSend("plate", -8.0), ReverbSend("hall", -14.0)]),
        "vocal_backup":InstrumentRole(eq=vocal_backup(), comp=comp_vocal(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -8.0)]),
        "vocal_chop":  InstrumentRole(eq=vocal_chop(), volume_db=-7.0,
                                      sends=[ReverbSend("plate", -6.0)]),
    },
    aliases=default_aliases(["kick", "snare", "clap", "hats", "perc", "sub_bass", "bass_808",
                              "pluck_synth", "pad", "chord_stab", "piano",
                              "vocal_lead", "vocal_backup", "vocal_chop"]),
    sidechain=[
        SidechainSpec(source="kick", target="bass_808",   amount=0.55, attack_ms=3, release_ms=140),
        SidechainSpec(source="kick", target="sub_bass",   amount=0.50, attack_ms=3, release_ms=130),
        SidechainSpec(source="kick", target="pad",        amount=0.40, attack_ms=8, release_ms=180),
    ],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-10.0, true_peak_db=-1.0, stereo_width=1.1, limiter_character="warm",
        low_shelf_db=1.5, low_shelf_freq=60, high_shelf_db=1.5, high_shelf_freq=12000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "verse", "pre_chorus", "chorus", "verse2", "chorus2", "bridge", "chorus3", "outro"],
))
