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


def ride_cymbal() -> EQProfile:
    """Jazz ride: bright shimmer without harshness — HP high since it never
    carries low end, gentle presence bump so the ping cuts through comping."""
    return EQProfile(
        hp_freq=400.0,
        bands=[
            EQBand(freq=1000, gain_db=-1.0, q=1.0, shape="bell"),
            EQBand(freq=8000, gain_db=1.5, q=0.8, shape="bell"),
            EQBand(freq=13000, gain_db=1.5, q=0.7, shape="high_shelf"),
        ],
    )


def timpani_perc() -> EQProfile:
    """Orchestral percussion (timpani, taiko, cinematic hits): weight + transient click."""
    return EQProfile(
        hp_freq=35.0,
        bands=[
            EQBand(freq=90, gain_db=2.0, q=0.9, shape="bell"),
            EQBand(freq=400, gain_db=-2.0, q=1.2, shape="bell"),
            EQBand(freq=4000, gain_db=1.5, q=1.2, shape="bell"),
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


def upright_bass() -> EQProfile:
    """Jazz double bass: warm low-mid body, no synthetic 'click' boost —
    the natural pluck/bow attack should stay untouched, roll off harsh top."""
    return EQProfile(
        hp_freq=35.0,
        bands=[
            EQBand(freq=100, gain_db=1.5, q=0.9, shape="bell"),
            EQBand(freq=300, gain_db=-1.5, q=1.2, shape="bell"),
            EQBand(freq=6000, gain_db=-1.5, q=0.7, shape="high_shelf"),
        ],
    )


def slap_bass() -> EQProfile:
    """Funk slap bass: thumb-thump weight + string-snap bite at 2-3kHz —
    the snap is the whole point, don't smooth it out."""
    return EQProfile(
        hp_freq=40.0,
        bands=[
            EQBand(freq=100, gain_db=1.5, q=1.0, shape="bell"),
            EQBand(freq=400, gain_db=-2.5, q=1.2, shape="bell"),
            EQBand(freq=2200, gain_db=2.5, q=1.2, shape="bell"),
            EQBand(freq=6000, gain_db=1.0, q=0.7, shape="high_shelf"),
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


def piano_jazz() -> EQProfile:
    """Acoustic jazz piano: natural body, no aggressive presence push —
    let the harmonic voicings sit un-hyped in the mix."""
    return EQProfile(
        hp_freq=50.0,
        bands=[
            EQBand(freq=250, gain_db=-1.0, q=1.0, shape="bell"),
            EQBand(freq=2500, gain_db=1.0, q=1.0, shape="bell"),
            EQBand(freq=9000, gain_db=1.0, q=0.7, shape="high_shelf"),
        ],
    )


def electric_piano() -> EQProfile:
    """Rhodes/Wurlitzer for funk & soul: warm bell mids, tine bite up top."""
    return EQProfile(
        hp_freq=70.0,
        bands=[
            EQBand(freq=200, gain_db=-1.0, q=1.0, shape="bell"),
            EQBand(freq=800, gain_db=1.0, q=1.2, shape="bell"),
            EQBand(freq=4500, gain_db=1.5, q=1.0, shape="bell"),
        ],
    )


def horns_section() -> EQProfile:
    """Funk/soul/jazz horn section (sax/trumpet/trombone stack): cut mud,
    push the honk/bite in the 2-4kHz range that cuts through a dense mix."""
    return EQProfile(
        hp_freq=150.0,
        bands=[
            EQBand(freq=400, gain_db=-2.0, q=1.2, shape="bell"),
            EQBand(freq=2500, gain_db=2.0, q=1.1, shape="bell"),
            EQBand(freq=8000, gain_db=1.0, q=0.7, shape="high_shelf"),
        ],
    )


def strings_section() -> EQProfile:
    """Orchestral strings (violin/viola/cello/bass ensemble): warmth without
    boxiness, gentle presence lift, natural air — no synth-style top-shelf hype."""
    return EQProfile(
        hp_freq=80.0,
        bands=[
            EQBand(freq=250, gain_db=1.0, q=0.9, shape="bell"),
            EQBand(freq=500, gain_db=-1.0, q=1.2, shape="bell"),
            EQBand(freq=4000, gain_db=1.0, q=1.0, shape="bell"),
            EQBand(freq=11000, gain_db=1.0, q=0.7, shape="high_shelf"),
        ],
    )


def brass_orchestral() -> EQProfile:
    """Orchestral brass section: power in the low-mids, controlled bite —
    less aggressive than a funk horn stack, meant to blend not cut."""
    return EQProfile(
        hp_freq=100.0,
        bands=[
            EQBand(freq=300, gain_db=1.0, q=0.9, shape="bell"),
            EQBand(freq=600, gain_db=-1.0, q=1.2, shape="bell"),
            EQBand(freq=3000, gain_db=1.5, q=1.0, shape="bell"),
        ],
    )


def woodwinds() -> EQProfile:
    """Flute/clarinet/oboe/bassoon section: preserve natural breathiness,
    gentle presence, no harsh top-end push."""
    return EQProfile(
        hp_freq=150.0,
        bands=[
            EQBand(freq=500, gain_db=-1.0, q=1.2, shape="bell"),
            EQBand(freq=3000, gain_db=1.0, q=1.0, shape="bell"),
            EQBand(freq=10000, gain_db=0.5, q=0.7, shape="high_shelf"),
        ],
    )


def choir() -> EQProfile:
    """Choir/vocal ensemble: warmth, presence for diction, air on top."""
    return EQProfile(
        hp_freq=120.0,
        bands=[
            EQBand(freq=300, gain_db=-1.0, q=1.2, shape="bell"),
            EQBand(freq=3000, gain_db=1.5, q=1.0, shape="bell"),
            EQBand(freq=11000, gain_db=1.5, q=0.7, shape="high_shelf"),
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


def vocal_soul() -> EQProfile:
    """Soul/funk lead vocal: warm and forward without the aggressive
    de-boxing pop vocals get — some low-mid warmth is the point."""
    return EQProfile(
        hp_freq=90.0,
        bands=[
            EQBand(freq=250, gain_db=-1.0, q=1.2, shape="bell"),
            EQBand(freq=3000, gain_db=1.5, q=1.2, shape="bell"),
            EQBand(freq=10000, gain_db=1.5, q=0.7, shape="high_shelf"),
        ],
    )


def vocal_jazz() -> EQProfile:
    """Jazz vocal: natural, minimal shaping — let the mic/performance speak,
    just clean up mud and add a touch of air."""
    return EQProfile(
        hp_freq=90.0,
        bands=[
            EQBand(freq=250, gain_db=-1.0, q=1.2, shape="bell"),
            EQBand(freq=9000, gain_db=1.0, q=0.7, shape="high_shelf"),
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


def comp_jazz_gentle() -> CompProfile:
    """Barely-there — jazz dynamics ARE the performance. Slow attack lets
    transients through untouched; this only catches the occasional peak."""
    return CompProfile(
        threshold_db=-20.0, ratio=1.8, attack_ms=25.0, release_ms=200.0,
        makeup_db=1.0, knee_db=8.0,
    )


def comp_orchestral_glue() -> CompProfile:
    """Bus glue only, not dynamics control — orchestral mixing preserves the
    performance's natural dynamic range. Never audible as 'compression'."""
    return CompProfile(
        threshold_db=-18.0, ratio=1.3, attack_ms=40.0, release_ms=250.0,
        makeup_db=0.5, knee_db=8.0,
    )


def comp_funk_punch() -> CompProfile:
    """Faster than jazz, still musical — catches the groove's transients to
    tighten the pocket without squashing the snap that makes funk funky."""
    return CompProfile(
        threshold_db=-14.0, ratio=3.5, attack_ms=6.0, release_ms=90.0,
        makeup_db=2.0, knee_db=3.0,
    )


def comp_soul_vocal() -> CompProfile:
    """Warmer/slower than the pop vocal comp — rides the performance instead
    of flattening it; soul vocals live and die on dynamic phrasing."""
    return CompProfile(
        threshold_db=-18.0, ratio=2.5, attack_ms=15.0, release_ms=150.0,
        makeup_db=2.0, knee_db=5.0,
    )


def comp_horns() -> CompProfile:
    """Light glue to tame section peaks without killing the honk."""
    return CompProfile(
        threshold_db=-14.0, ratio=2.5, attack_ms=10.0, release_ms=100.0,
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
    "upright_bass":  ["upright", "upright bass", "double bass", "acoustic bass"],
    "slap_bass":     ["slap", "slap bass"],

    "lead_synth":    ["lead", "synth lead", "topline"],
    "pluck_synth":   ["pluck", "arp"],
    "pad":           ["pad", "strings", "atmo"],
    "chord_stab":    ["stab", "chord", "chords"],
    "piano":         ["piano", "keys", "rhodes", "wurli"],
    "electric_piano": ["rhodes", "wurli", "wurlitzer", "ep", "clav", "clavinet"],

    "vocal_lead":    ["vox", "vocal", "lead vocal", "voc"],
    "vocal_backup":  ["bg vocal", "backup", "bv"],
    "vocal_chop":    ["vocal chop", "chop", "vocoded"],
    "choir":         ["choir", "vocal ensemble"],

    "rhythm_guitar": ["rhythm", "rhy gtr", "gtr"],
    "lead_guitar":   ["lead gtr", "solo gtr"],
    "clean_guitar":  ["clean gtr", "acoustic"],

    "ride":          ["ride"],
    "horns_section": ["horns", "horn section", "sax", "trumpet", "trombone", "brass"],
    "strings_section": ["string section", "strings", "violin", "viola", "cello", "orchestra strings"],
    "brass_orchestral": ["orch brass", "french horn", "orchestral brass"],
    "woodwinds":     ["woodwind", "flute", "clarinet", "oboe", "bassoon"],
    "timpani_perc":  ["timpani", "orch perc", "taiko", "cinematic hit"],

    "riser_fx":      ["riser", "sweep", "uplifter"],
    "impact_fx":     ["impact", "hit", "downlifter", "boom"],
}


def default_aliases(roles: list[str]) -> dict[str, list[str]]:
    """Pick aliases for the roles this style uses."""
    return {r: ALIASES[r] for r in roles if r in ALIASES}
