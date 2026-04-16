"""Shared instrument-role EQ/comp library used by multiple styles.

These are baseline curves — individual style files override specific fields
when the genre demands it (e.g. dubstep kick is weightier than deep-house kick).
Industry-standard starting points: aggressive HP, realistic cut/boost curves.
"""

from reaper_mcp.mix_engine.profiles_v2 import EQBand, EQProfile, CompProfile


# ───────────────────────── DRUMS ─────────────────────────

def kick_edm(punchy: bool = True) -> EQProfile:
    """EDM kick: weight at 60Hz, cut boxy 200-400Hz, click at 3-5kHz."""
    return EQProfile(
        hp_freq=25.0,
        bands=[
            EQBand(freq=60, gain_db=2.0, q=1.2, shape="bell"),
            EQBand(freq=250, gain_db=-3.0, q=1.4, shape="bell"),
            EQBand(freq=500, gain_db=-1.5, q=1.5, shape="bell"),
            EQBand(freq=3500 if punchy else 4500, gain_db=2.0, q=1.5, shape="bell"),
        ],
    )


def kick_acoustic() -> EQProfile:
    """Rock/pop acoustic kick: 80Hz body, cut mud, beater click at 3kHz."""
    return EQProfile(
        hp_freq=30.0,
        bands=[
            EQBand(freq=80, gain_db=2.0, q=1.2, shape="bell"),
            EQBand(freq=350, gain_db=-3.0, q=1.4, shape="bell"),
            EQBand(freq=3000, gain_db=2.5, q=1.5, shape="bell"),
        ],
    )


def snare_edm() -> EQProfile:
    return EQProfile(
        hp_freq=100.0,
        bands=[
            EQBand(freq=200, gain_db=1.5, q=1.2, shape="bell"),
            EQBand(freq=500, gain_db=-2.0, q=1.5, shape="bell"),
            EQBand(freq=5000, gain_db=2.0, q=1.2, shape="bell"),
            EQBand(freq=12000, gain_db=2.0, q=0.7, shape="high_shelf"),
        ],
    )


def snare_acoustic() -> EQProfile:
    """Rock snare: body at 200Hz, crack at 3-5kHz, cut ring at 800Hz."""
    return EQProfile(
        hp_freq=80.0,
        bands=[
            EQBand(freq=200, gain_db=2.0, q=1.0, shape="bell"),
            EQBand(freq=800, gain_db=-2.5, q=1.5, shape="bell"),
            EQBand(freq=5000, gain_db=3.0, q=1.2, shape="bell"),
            EQBand(freq=10000, gain_db=1.5, q=0.7, shape="high_shelf"),
        ],
    )


def hats() -> EQProfile:
    return EQProfile(
        hp_freq=500.0,
        bands=[
            EQBand(freq=300, gain_db=-3.0, q=1.0, shape="bell"),
            EQBand(freq=8000, gain_db=2.0, q=0.8, shape="bell"),
            EQBand(freq=14000, gain_db=2.5, q=0.7, shape="high_shelf"),
        ],
    )


def perc_bright() -> EQProfile:
    return EQProfile(
        hp_freq=200.0,
        bands=[
            EQBand(freq=2500, gain_db=1.5, q=1.0, shape="bell"),
            EQBand(freq=12000, gain_db=2.0, q=0.7, shape="high_shelf"),
        ],
    )


def drums_bus() -> EQProfile:
    return EQProfile(
        hp_freq=25.0,
        bands=[
            EQBand(freq=500, gain_db=-1.5, q=1.2, shape="bell"),
            EQBand(freq=10000, gain_db=1.0, q=0.7, shape="high_shelf"),
        ],
    )


# ───────────────────────── BASS ─────────────────────────

def sub_bass() -> EQProfile:
    """Pure sub: mono-ish, HP at 25Hz, low shelf weight, cut anything above 200Hz."""
    return EQProfile(
        hp_freq=25.0,
        bands=[
            EQBand(freq=50, gain_db=1.5, q=0.8, shape="low_shelf"),
            EQBand(freq=300, gain_db=-6.0, q=1.0, shape="bell"),
            EQBand(freq=2000, gain_db=-4.0, q=0.7, shape="high_shelf"),
        ],
    )


def mid_bass() -> EQProfile:
    """Mid-bass / reese / wobble: 100-250Hz body, bite at 800-1500Hz."""
    return EQProfile(
        hp_freq=40.0,
        bands=[
            EQBand(freq=150, gain_db=1.5, q=1.0, shape="bell"),
            EQBand(freq=400, gain_db=-2.0, q=1.2, shape="bell"),
            EQBand(freq=1200, gain_db=1.5, q=1.0, shape="bell"),
        ],
    )


def bass_guitar() -> EQProfile:
    return EQProfile(
        hp_freq=40.0,
        bands=[
            EQBand(freq=90, gain_db=1.5, q=1.0, shape="bell"),
            EQBand(freq=400, gain_db=-2.0, q=1.2, shape="bell"),
            EQBand(freq=2500, gain_db=2.0, q=1.0, shape="bell"),
        ],
    )


def bass_808() -> EQProfile:
    """Trap 808: sub weight + saturation bite so it cuts through on small speakers."""
    return EQProfile(
        hp_freq=25.0,
        bands=[
            EQBand(freq=50, gain_db=1.0, q=0.8, shape="low_shelf"),
            EQBand(freq=200, gain_db=-2.0, q=1.2, shape="bell"),
            EQBand(freq=800, gain_db=1.5, q=1.0, shape="bell"),
            EQBand(freq=3500, gain_db=-2.0, q=0.7, shape="high_shelf"),
        ],
    )


# ───────────────────────── SYNTHS / KEYS ─────────────────────────

def lead_synth() -> EQProfile:
    """Big-room / festival lead: cuts through at 3kHz, HP at 150 to avoid mud."""
    return EQProfile(
        hp_freq=150.0,
        bands=[
            EQBand(freq=400, gain_db=-2.0, q=1.2, shape="bell"),
            EQBand(freq=3000, gain_db=2.0, q=1.2, shape="bell"),
            EQBand(freq=10000, gain_db=1.5, q=0.7, shape="high_shelf"),
        ],
    )


def pluck_synth() -> EQProfile:
    return EQProfile(
        hp_freq=200.0,
        bands=[
            EQBand(freq=600, gain_db=-1.5, q=1.2, shape="bell"),
            EQBand(freq=4000, gain_db=1.5, q=1.0, shape="bell"),
            EQBand(freq=12000, gain_db=1.5, q=0.7, shape="high_shelf"),
        ],
    )


def pad() -> EQProfile:
    """Pad gets sidechained heavily — low HP to not compete with sub, slight high shelf for air."""
    return EQProfile(
        hp_freq=200.0,
        bands=[
            EQBand(freq=400, gain_db=-1.5, q=1.2, shape="bell"),
            EQBand(freq=10000, gain_db=1.5, q=0.7, shape="high_shelf"),
        ],
    )


def chord_stab() -> EQProfile:
    """Pitched chord stab (future bass, chillstep): punchy mids, bright top."""
    return EQProfile(
        hp_freq=150.0,
        bands=[
            EQBand(freq=500, gain_db=-1.5, q=1.2, shape="bell"),
            EQBand(freq=3500, gain_db=2.0, q=1.0, shape="bell"),
            EQBand(freq=12000, gain_db=2.0, q=0.7, shape="high_shelf"),
        ],
    )


def piano_modern() -> EQProfile:
    return EQProfile(
        hp_freq=60.0,
        bands=[
            EQBand(freq=300, gain_db=-1.5, q=1.0, shape="bell"),
            EQBand(freq=3000, gain_db=1.5, q=1.0, shape="bell"),
            EQBand(freq=10000, gain_db=1.5, q=0.7, shape="high_shelf"),
        ],
    )


# ───────────────────────── VOCALS ─────────────────────────

def vocal_lead() -> EQProfile:
    """Modern pop/EDM vocal: HP 100Hz, cut box at 300Hz, presence 3-5kHz, air 12k+."""
    return EQProfile(
        hp_freq=100.0,
        bands=[
            EQBand(freq=300, gain_db=-2.0, q=1.2, shape="bell"),
            EQBand(freq=1000, gain_db=-1.0, q=1.5, shape="bell"),
            EQBand(freq=4000, gain_db=2.0, q=1.2, shape="bell"),
            EQBand(freq=12000, gain_db=2.0, q=0.7, shape="high_shelf"),
        ],
    )


def vocal_backup() -> EQProfile:
    return EQProfile(
        hp_freq=150.0,
        bands=[
            EQBand(freq=300, gain_db=-2.0, q=1.2, shape="bell"),
            EQBand(freq=5000, gain_db=1.5, q=1.0, shape="bell"),
        ],
    )


def vocal_chop() -> EQProfile:
    """Pitched vocal chop (future bass / chillstep): bright, present, high shelf lift."""
    return EQProfile(
        hp_freq=200.0,
        bands=[
            EQBand(freq=400, gain_db=-1.5, q=1.2, shape="bell"),
            EQBand(freq=4000, gain_db=1.5, q=1.0, shape="bell"),
            EQBand(freq=12000, gain_db=2.5, q=0.7, shape="high_shelf"),
        ],
    )


# ───────────────────────── GUITARS ─────────────────────────

def rhythm_guitar() -> EQProfile:
    return EQProfile(
        hp_freq=100.0,
        bands=[
            EQBand(freq=300, gain_db=-2.0, q=1.2, shape="bell"),
            EQBand(freq=3000, gain_db=1.5, q=1.0, shape="bell"),
            EQBand(freq=8000, gain_db=-1.5, q=0.7, shape="high_shelf"),
        ],
    )


def lead_guitar() -> EQProfile:
    return EQProfile(
        hp_freq=150.0,
        bands=[
            EQBand(freq=500, gain_db=-1.5, q=1.2, shape="bell"),
            EQBand(freq=2500, gain_db=2.0, q=1.0, shape="bell"),
        ],
    )


def clean_guitar() -> EQProfile:
    return EQProfile(
        hp_freq=80.0,
        bands=[
            EQBand(freq=300, gain_db=-1.5, q=1.2, shape="bell"),
            EQBand(freq=4000, gain_db=1.5, q=1.0, shape="bell"),
            EQBand(freq=12000, gain_db=1.5, q=0.7, shape="high_shelf"),
        ],
    )


# ───────────────────────── FX ─────────────────────────

def riser_fx() -> EQProfile:
    """Risers / build FX: HP to not clash with sub, bright top."""
    return EQProfile(
        hp_freq=200.0,
        bands=[
            EQBand(freq=12000, gain_db=2.0, q=0.7, shape="high_shelf"),
        ],
    )


def impact_fx() -> EQProfile:
    """Impacts / downlifters: huge low-end weight."""
    return EQProfile(
        hp_freq=25.0,
        bands=[
            EQBand(freq=60, gain_db=2.0, q=0.8, shape="low_shelf"),
            EQBand(freq=400, gain_db=-2.0, q=1.2, shape="bell"),
        ],
    )


# ───────────────────────── COMPRESSION PRESETS ─────────────────────────

def comp_kick_edm() -> CompProfile:
    return CompProfile(
        threshold_db=-10.0, ratio=4.0, attack_ms=3.0, release_ms=100.0,
        makeup_db=2.0, knee_db=2.0,
    )


def comp_snare_edm() -> CompProfile:
    return CompProfile(
        threshold_db=-12.0, ratio=3.5, attack_ms=5.0, release_ms=80.0,
        makeup_db=2.0, knee_db=3.0,
    )


def comp_bass_edm() -> CompProfile:
    """Glue comp for bass, tight attack to catch peaks."""
    return CompProfile(
        threshold_db=-14.0, ratio=4.0, attack_ms=2.0, release_ms=120.0,
        makeup_db=3.0, knee_db=2.0,
    )


def comp_vocal() -> CompProfile:
    return CompProfile(
        threshold_db=-16.0, ratio=3.0, attack_ms=8.0, release_ms=100.0,
        makeup_db=2.5, knee_db=4.0,
    )


def comp_lead_synth() -> CompProfile:
    return CompProfile(
        threshold_db=-14.0, ratio=3.0, attack_ms=10.0, release_ms=120.0,
        makeup_db=2.0, knee_db=4.0,
    )


def comp_pad() -> CompProfile:
    """Gentle glue; the SIDECHAIN does the real pumping."""
    return CompProfile(
        threshold_db=-18.0, ratio=2.0, attack_ms=30.0, release_ms=200.0,
        makeup_db=1.5, knee_db=6.0,
    )


def comp_drums_bus() -> CompProfile:
    return CompProfile(
        threshold_db=-12.0, ratio=3.0, attack_ms=15.0, release_ms=100.0,
        makeup_db=2.0, knee_db=4.0,
    )


def comp_master_transparent() -> CompProfile:
    return CompProfile(
        threshold_db=-12.0, ratio=1.5, attack_ms=30.0, release_ms=200.0,
        makeup_db=1.5, knee_db=6.0,
    )


def comp_master_glue() -> CompProfile:
    return CompProfile(
        threshold_db=-10.0, ratio=2.0, attack_ms=30.0, release_ms=150.0,
        makeup_db=1.5, knee_db=4.0,
    )


# ───────────────────────── TRACK-NAME ALIAS LIBRARY ─────────────────────────

ALIASES = {
    "kick":          ["kick", "bd", "bass drum", "kik"],
    "snare":         ["snare", "snr", "sd", "clap"],
    "clap":          ["clap", "clp"],
    "hats":          ["hat", "hh", "hihat", "hi hat"],
    "open_hat":      ["open hat", "oh "],
    "perc":          ["perc", "shaker", "tamb", "ride", "crash"],
    "toms":          ["tom"],
    "cymbals":       ["cymbal", "crash", "ride"],
    "drums_bus":     ["drums bus", "drum bus"],

    "sub_bass":      ["sub", "sub bass", "808 sub"],
    "bass":          ["bass"],
    "reese_bass":    ["reese"],
    "growl_bass":    ["growl", "wobble", "dubstep bass", "wub"],
    "bass_808":      ["808"],
    "bass_guitar":   ["bass gtr", "bass guitar", "elec bass"],

    "lead_synth":    ["lead", "synth lead", "topline"],
    "pluck_synth":   ["pluck", "arp"],
    "pad":           ["pad", "strings", "atmo"],
    "chord_stab":    ["stab", "chord", "chords"],
    "piano":         ["piano", "keys", "rhodes", "wurli"],

    "vocal_lead":    ["vox", "vocal", "lead vocal", "voc"],
    "vocal_backup":  ["bg vocal", "backup", "bv"],
    "vocal_chop":    ["vocal chop", "chop", "vocoded"],

    "rhythm_guitar": ["rhythm", "rhy gtr", "gtr"],
    "lead_guitar":   ["lead gtr", "solo gtr"],
    "clean_guitar":  ["clean gtr", "acoustic"],

    "riser_fx":      ["riser", "sweep", "uplifter"],
    "impact_fx":     ["impact", "hit", "downlifter", "boom"],
}


def default_aliases(roles: list[str]) -> dict[str, list[str]]:
    """Pick aliases for the roles this style uses."""
    return {r: ALIASES[r] for r in roles if r in ALIASES}
