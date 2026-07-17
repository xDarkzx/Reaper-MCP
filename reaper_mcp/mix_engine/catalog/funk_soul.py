"""Funk & soul style profiles — 4 subgenres. Defining technique: the pocket
comes from performance, not compression — comps here catch transients for
punch without squashing the groove. Sidechain is used sparingly and only
where pros genuinely use it in these genres (a keys/horns duck under lead
vocal ad-libs, not a kick/bass duck — funk bass and kick play IN UNISON,
ducking one under the other fights the pocket instead of serving it).
"""

from reaper_mcp.mix_engine.profiles_v2 import (
    StyleProfile, InstrumentRole, SidechainSpec, MasteringChain, ReverbSend,
    register_profile, DEFAULT_REVERB_BUSES,
)
from reaper_mcp.mix_engine.catalog._shared import (
    kick_acoustic, snare_acoustic, hats, perc_bright,
    slap_bass, bass_guitar, electric_piano, rhythm_guitar, clean_guitar,
    strings_section, horns_section, vocal_soul, vocal_backup,
    comp_funk_punch, comp_soul_vocal, comp_horns, comp_bass_edm,
    comp_master_glue, comp_master_transparent,
    default_aliases,
)


# ═════════════════════════════════════════════════════════════════
# CLASSIC FUNK — JB's-style: tight kit, slap/pop bass, horn stabs,
# chicken-scratch rhythm guitar. Punchy but never brickwalled.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="classic_funk",
    family="funk_soul",
    bpm_range=(95, 118),
    key_hints=["dorian", "mixolydian", "minor"],
    instrument_roles={
        "kick":          InstrumentRole(eq=kick_acoustic(), comp=comp_funk_punch(), volume_db=-2.0),
        "snare":         InstrumentRole(eq=snare_acoustic(), comp=comp_funk_punch(), volume_db=-2.0,
                                         sends=[ReverbSend("room", -11.0)]),
        "hats":          InstrumentRole(eq=hats(), volume_db=-9.0, pan=0.2),
        "perc":          InstrumentRole(eq=perc_bright(), volume_db=-11.0, pan=-0.2),
        "slap_bass":     InstrumentRole(eq=slap_bass(), comp=comp_bass_edm(), volume_db=-2.0),
        "electric_piano": InstrumentRole(eq=electric_piano(), volume_db=-6.0, pan=-0.25,
                                          sends=[ReverbSend("plate", -12.0)]),
        "rhythm_guitar": InstrumentRole(eq=rhythm_guitar(), volume_db=-5.0, pan=0.35,
                                         sends=[ReverbSend("room", -13.0)]),
        "horns_section": InstrumentRole(eq=horns_section(), comp=comp_horns(), volume_db=-3.0,
                                         sends=[ReverbSend("room", -10.0)]),
        "vocal_lead":    InstrumentRole(eq=vocal_soul(), comp=comp_soul_vocal(), volume_db=-2.0,
                                         sends=[ReverbSend("plate", -9.0), ReverbSend("room", -12.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "perc", "slap_bass",
                              "electric_piano", "rhythm_guitar", "horns_section", "vocal_lead"]),
    sidechain=[],  # kick and bass play the pocket together — no ducking between them
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-10.0, true_peak_db=-1.0, stereo_width=1.05, limiter_character="warm",
        low_shelf_db=0.5, low_shelf_freq=80, high_shelf_db=0.5, high_shelf_freq=10000,
        bus_comp=comp_master_glue(),
    ),
    structure_hints=["intro", "groove", "verse", "chorus", "breakdown", "horn_hits", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# MOTOWN SOUL — string-laden, mid-tempo, vocal-forward, smooth.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="motown_soul",
    family="funk_soul",
    bpm_range=(85, 115),
    key_hints=["major", "minor", "mixolydian"],
    instrument_roles={
        "kick":          InstrumentRole(eq=kick_acoustic(), comp=comp_funk_punch(), volume_db=-4.0),
        "snare":         InstrumentRole(eq=snare_acoustic(), comp=comp_funk_punch(), volume_db=-3.0,
                                         sends=[ReverbSend("room", -9.0), ReverbSend("plate", -12.0)]),
        "hats":          InstrumentRole(eq=hats(), volume_db=-11.0, pan=0.2),
        "bass_guitar":   InstrumentRole(eq=bass_guitar(), comp=comp_bass_edm(), volume_db=-3.0),
        "electric_piano": InstrumentRole(eq=electric_piano(), volume_db=-6.0, pan=-0.2,
                                          sends=[ReverbSend("plate", -10.0)]),
        "strings_section": InstrumentRole(eq=strings_section(), volume_db=-6.0,
                                           sends=[ReverbSend("hall", -6.0)]),
        "horns_section": InstrumentRole(eq=horns_section(), comp=comp_horns(), volume_db=-5.0,
                                         sends=[ReverbSend("room", -10.0)]),
        "vocal_lead":    InstrumentRole(eq=vocal_soul(), comp=comp_soul_vocal(), volume_db=-2.0,
                                         sends=[ReverbSend("plate", -8.0), ReverbSend("hall", -13.0)]),
        "vocal_backup":  InstrumentRole(eq=vocal_backup(), comp=comp_soul_vocal(), volume_db=-6.0,
                                         sends=[ReverbSend("plate", -9.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "bass_guitar", "electric_piano",
                              "strings_section", "horns_section", "vocal_lead", "vocal_backup"]),
    sidechain=[],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-12.0, true_peak_db=-1.0, stereo_width=1.1, limiter_character="warm",
        low_shelf_db=0.5, low_shelf_freq=80, high_shelf_db=1.0, high_shelf_freq=11000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "verse", "chorus", "verse2", "chorus2", "bridge", "chorus3", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# NEO SOUL — laid-back modern soul: Rhodes-heavy, behind-the-beat pocket,
# subtle electronic touches. The one style here that legitimately uses a
# light sidechain — keys/horns duck a touch under lead vocal ad-libs, a
# real technique modern neo-soul engineers use to keep the vocal forward
# without riding a fader through every phrase.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="neo_soul",
    family="funk_soul",
    bpm_range=(70, 100),
    key_hints=["dorian", "minor", "lydian"],
    instrument_roles={
        "kick":          InstrumentRole(eq=kick_acoustic(), comp=comp_funk_punch(), volume_db=-4.0),
        "snare":         InstrumentRole(eq=snare_acoustic(), comp=comp_funk_punch(), volume_db=-4.0,
                                         sends=[ReverbSend("room", -11.0)]),
        "hats":          InstrumentRole(eq=hats(), volume_db=-11.0, pan=0.2),
        "bass_guitar":   InstrumentRole(eq=bass_guitar(), comp=comp_bass_edm(), volume_db=-3.0),
        "electric_piano": InstrumentRole(eq=electric_piano(), volume_db=-5.0, pan=-0.2,
                                          sends=[ReverbSend("plate", -11.0)]),
        "horns_section": InstrumentRole(eq=horns_section(), comp=comp_horns(), volume_db=-6.0,
                                         sends=[ReverbSend("room", -11.0)]),
        "vocal_lead":    InstrumentRole(eq=vocal_soul(), comp=comp_soul_vocal(), volume_db=-2.0,
                                         sends=[ReverbSend("plate", -9.0), ReverbSend("hall", -13.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "bass_guitar", "electric_piano",
                              "horns_section", "vocal_lead"]),
    sidechain=[
        # Subtle, musical duck — NOT an EDM pump. Low amount, slow release
        # so it reads as "the vocal breathes room" rather than audible pumping.
        SidechainSpec(source="vocal_lead", target="electric_piano", amount=0.25, attack_ms=15, release_ms=220),
        SidechainSpec(source="vocal_lead", target="horns_section",  amount=0.20, attack_ms=15, release_ms=220),
    ],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-13.0, true_peak_db=-1.0, stereo_width=1.1, limiter_character="warm",
        low_shelf_db=0.5, low_shelf_freq=70, high_shelf_db=0.5, high_shelf_freq=10000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "verse", "hook", "verse2", "hook2", "bridge", "hook3", "outro"],
))


# ═════════════════════════════════════════════════════════════════
# DISCO FUNK — uptempo four-on-the-floor cousin of funk, string stabs,
# four-on-floor kick, the one funk-family style close enough to dance
# music to use a real kick-driven pump on pads/strings.
# ═════════════════════════════════════════════════════════════════

register_profile(StyleProfile(
    name="disco_funk",
    family="funk_soul",
    bpm_range=(110, 128),
    key_hints=["major", "minor", "mixolydian"],
    instrument_roles={
        "kick":          InstrumentRole(eq=kick_acoustic(), comp=comp_funk_punch(), volume_db=-2.0),
        "snare":         InstrumentRole(eq=snare_acoustic(), comp=comp_funk_punch(), volume_db=-2.0,
                                         sends=[ReverbSend("plate", -9.0)]),
        "hats":          InstrumentRole(eq=hats(), volume_db=-8.0, pan=0.2),
        "perc":          InstrumentRole(eq=perc_bright(), volume_db=-10.0, pan=-0.2),
        "bass_guitar":   InstrumentRole(eq=bass_guitar(), comp=comp_bass_edm(), volume_db=-2.0),
        "electric_piano": InstrumentRole(eq=electric_piano(), volume_db=-6.0, pan=-0.2,
                                          sends=[ReverbSend("plate", -10.0)]),
        "strings_section": InstrumentRole(eq=strings_section(), volume_db=-5.0,
                                           sends=[ReverbSend("hall", -6.0)]),
        "horns_section": InstrumentRole(eq=horns_section(), comp=comp_horns(), volume_db=-4.0,
                                         sends=[ReverbSend("room", -9.0)]),
        "vocal_lead":    InstrumentRole(eq=vocal_soul(), comp=comp_soul_vocal(), volume_db=-2.0,
                                         sends=[ReverbSend("plate", -8.0), ReverbSend("hall", -12.0)]),
    },
    aliases=default_aliases(["kick", "snare", "hats", "perc", "bass_guitar", "electric_piano",
                              "strings_section", "horns_section", "vocal_lead"]),
    sidechain=[
        SidechainSpec(source="kick", target="strings_section", amount=0.35, attack_ms=5, release_ms=160),
    ],
    reverb_buses=DEFAULT_REVERB_BUSES.copy(),
    mastering=MasteringChain(
        target_lufs=-9.0, true_peak_db=-1.0, stereo_width=1.1, limiter_character="transparent",
        low_shelf_db=0.5, low_shelf_freq=80, high_shelf_db=1.0, high_shelf_freq=11000,
        bus_comp=comp_master_transparent(),
    ),
    structure_hints=["intro", "verse", "chorus", "verse2", "chorus2", "breakdown", "chorus3", "outro"],
))
