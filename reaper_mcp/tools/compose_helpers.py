"""Compose helpers — shared constants and keyword matching for compose tools."""

import json
import re


# ============================================================
# Map REAPER track/instrument names to our instrument registry
# ============================================================
# Keywords in track name or VSTi name → registry instrument name.
# Checked longest-first so "french horn" beats "horn".
_INSTRUMENT_NAME_KEYWORDS = [
    # IMPORTANT: More specific keywords MUST come before general ones.
    # "bassoon" before "bass", "bass trombone" before "bass", etc.
    # Includes Italian, French, German names + common DAW abbreviations.

    # ── Strings — specific first ──────────────────────────────────
    # Violin 1
    ("violin 1", "violin_1"), ("violin i", "violin_1"), ("violins 1", "violin_1"),
    ("1st violin", "violin_1"), ("vln 1", "violin_1"), ("vln1", "violin_1"),
    ("v1", "violin_1"), ("vl1", "violin_1"), ("viol 1", "violin_1"),
    ("violino 1", "violin_1"), ("violini 1", "violin_1"),  # Italian
    ("violon 1", "violin_1"), ("violons 1", "violin_1"),  # French
    ("violine 1", "violin_1"), ("violinen 1", "violin_1"),  # German
    ("1st vln", "violin_1"), ("first violin", "violin_1"),
    # Violin 2
    ("violin 2", "violin_2"), ("violin ii", "violin_2"), ("violins 2", "violin_2"),
    ("2nd violin", "violin_2"), ("vln 2", "violin_2"), ("vln2", "violin_2"),
    ("v2", "violin_2"), ("vl2", "violin_2"), ("viol 2", "violin_2"),
    ("violino 2", "violin_2"), ("violini 2", "violin_2"),  # Italian
    ("violon 2", "violin_2"), ("violons 2", "violin_2"),  # French
    ("violine 2", "violin_2"), ("violinen 2", "violin_2"),  # German
    ("2nd vln", "violin_2"), ("second violin", "violin_2"),
    # Viola (Italian = viola, French = alto, German = bratsche)
    ("viola", "viola"), ("violas", "viola"), ("vla", "viola"), ("vle", "viola"),
    ("viole", "viola"),  # Italian plural / French
    ("bratsche", "viola"), ("bratschen", "viola"),  # German
    ("alto", "viola"),  # French orchestral name
    # Cello (Italian = violoncello, French = violoncelle, German = violoncell)
    ("violoncello", "cello"), ("violoncelli", "cello"),  # Italian
    ("violoncelle", "cello"), ("violoncelles", "cello"),  # French
    ("cello", "cello"), ("celli", "cello"), ("cellos", "cello"),
    ("vcl", "cello"), ("vc", "cello"), ("vlc", "cello"),
    # Double Bass — MUST come before general "bass" (below)
    ("contrabass", "bass"), ("contrabasses", "bass"),
    ("contrebasse", "bass"), ("contrebasses", "bass"),  # French
    ("kontrabass", "bass"), ("kontrabasse", "bass"),  # German
    ("contrabbasso", "bass"), ("contrabassi", "bass"),  # Italian
    ("double bass", "bass"), ("string bass", "bass"),
    ("upright bass", "bass"),

    # ── Woodwinds — bassoon BEFORE general "bass" ─────────────────
    # Bassoon (Italian = fagotto, French = basson, German = fagott)
    ("contrabassoon", "bassoon"), ("contrebasson", "bassoon"),  # contra first
    ("contrafagotto", "bassoon"), ("kontrafagott", "bassoon"),
    ("bassoon", "bassoon"), ("bassoons", "bassoon"), ("bsn", "bassoon"),
    ("fagotto", "bassoon"), ("fagotti", "bassoon"),  # Italian
    ("basson", "bassoon"), ("bassons", "bassoon"),  # French
    ("fagott", "bassoon"), ("fagotte", "bassoon"),  # German
    # Piccolo (Italian = flauto piccolo/ottavino)
    ("piccolo", "piccolo"), ("picc", "piccolo"),
    ("ottavino", "piccolo"), ("flauto piccolo", "piccolo"),  # Italian
    ("petite flute", "piccolo"),  # French
    ("kleine flote", "piccolo"),  # German
    # Flute (Italian = flauto, French = flute, German = flote/querflote)
    ("flute", "flute"), ("flutes", "flute"), ("flt", "flute"), ("fl", "flute"),
    ("flauto", "flute"), ("flauti", "flute"),  # Italian
    ("flote", "flute"), ("querflote", "flute"),  # German
    # Oboe (Italian = oboe, French = hautbois, German = oboe/hoboe)
    ("oboe", "oboe"), ("oboes", "oboe"), ("ob", "oboe"),
    ("hautbois", "oboe"),  # French
    ("hoboe", "oboe"),  # German alt spelling
    ("cor anglais", "oboe"), ("english horn", "oboe"),  # English horn → oboe
    ("corno inglese", "oboe"),  # Italian for english horn
    # Clarinet (Italian = clarinetto, French = clarinette, German = klarinette)
    ("bass clarinet", "clarinet"), ("bass clar", "clarinet"),  # bass clar before "bass"
    ("clarinetto basso", "clarinet"), ("clarinette basse", "clarinet"),
    ("bassklarinette", "clarinet"),
    ("clarinet", "clarinet"), ("clarinets", "clarinet"), ("clar", "clarinet"),
    ("cl", "clarinet"), ("cla", "clarinet"),
    ("clarinetto", "clarinet"), ("clarinetti", "clarinet"),  # Italian
    ("clarinette", "clarinet"), ("clarinettes", "clarinet"),  # French
    ("klarinette", "clarinet"), ("klarinetten", "clarinet"),  # German

    # ── Brass — longer matches before shorter ─────────────────────
    # French Horn (Italian = corno, French = cor, German = horn/waldhorn)
    ("french horn", "french_horn"), ("french horns", "french_horn"),
    ("waldhorn", "french_horn"), ("waldhorner", "french_horn"),  # German
    ("corno", "french_horn"), ("corni", "french_horn"),  # Italian
    ("cor", "french_horn"),  # French (short — placed carefully)
    # Trombone (Italian = trombone, French = trombone, German = posaune)
    ("bass trombone", "trombone"), ("bass trb", "trombone"),
    ("tenor trombone", "trombone"), ("alto trombone", "trombone"),
    ("trombone", "trombone"), ("trombones", "trombone"),
    ("trb", "trombone"), ("tbn", "trombone"),
    ("posaune", "trombone"), ("posaunen", "trombone"),  # German
    # Trumpet (Italian = tromba, French = trompette, German = trompete)
    ("trumpet", "trumpet"), ("trumpets", "trumpet"),
    ("trp", "trumpet"), ("tpt", "trumpet"), ("trpt", "trumpet"),
    ("tromba", "trumpet"), ("trombe", "trumpet"),  # Italian
    ("trompette", "trumpet"), ("trompettes", "trumpet"),  # French
    ("trompete", "trumpet"), ("trompeten", "trumpet"),  # German
    # Tuba (same in all languages, German = tuba)
    ("tuba", "tuba"), ("tubas", "tuba"), ("tba", "tuba"),
    # Horn general — AFTER french horn, trombone, trumpet, tuba
    ("horn", "french_horn"), ("horns", "french_horn"), ("hrn", "french_horn"),
    ("hn", "french_horn"),

    # ── Strings general — AFTER all brass/woodwind containing "bass" ──
    ("basses", "bass"), ("bass", "bass"), ("cb", "bass"), ("kb", "bass"),
    ("bassi", "bass"),  # Italian plural

    # ── Percussion ────────────────────────────────────────────────
    # Timpani (Italian = timpani, French = timbales, German = pauken)
    ("timpani", "timpani"), ("timp", "timpani"),
    ("timbales", "timpani"),  # French
    ("pauken", "timpani"), ("pauke", "timpani"),  # German
    ("kettledrum", "timpani"), ("kettle drum", "timpani"),
    # Tuned percussion
    ("tuned perc", "tuned_percussion"), ("tuned_perc", "tuned_percussion"),
    ("glockenspiel", "tuned_percussion"), ("glock", "tuned_percussion"),
    ("xylophone", "tuned_percussion"), ("xylo", "tuned_percussion"),
    ("marimba", "tuned_percussion"),
    ("vibraphone", "tuned_percussion"), ("vibes", "tuned_percussion"),
    ("tubular bell", "tuned_percussion"), ("chimes", "tuned_percussion"),
    ("campane", "tuned_percussion"),  # Italian for tubular bells
    ("crotales", "tuned_percussion"),
    ("celesta", "tuned_percussion"), ("celeste", "tuned_percussion"),
    # HZ Percussion (Kontakt) — LONGER matches first to avoid "hz taiko" eating all 3
    ("lo taiko", "hz_lo_taiko"), ("low taiko", "hz_lo_taiko"), ("taiko lo", "hz_lo_taiko"),
    ("boobam", "hz_boobams"), ("boo bam", "hz_boobams"), ("boobams", "hz_boobams"),
    ("boombam", "hz_boobams"), ("boombams", "hz_boobams"),
    ("taiko es", "hz_taiko"), ("taiko ensemble", "hz_taiko"), ("taikoes", "hz_taiko"),
    ("taiko hi", "hz_taiko"), ("hz taiko", "hz_taiko"),
    # General percussion — fallback
    ("percussion", "timpani"), ("perc", "timpani"),
    ("schlagzeug", "timpani"),  # German for percussion

    # ── Ethnic / Solo instruments ─────────────────────────────────
    ("duduk", "duduk"), ("daduk", "duduk"), ("doudouk", "duduk"),

    # ── Keys / Plucked ────────────────────────────────────────────
    # Harp (Italian = arpa, French = harpe, German = harfe)
    ("harp", "harp"), ("harps", "harp"),
    ("arpa", "harp"), ("arpe", "harp"),  # Italian
    ("harpe", "harp"), ("harpes", "harp"),  # French
    ("harfe", "harp"), ("harfen", "harp"),  # German
    # Piano (Italian = pianoforte, French = piano, German = klavier)
    ("pianoforte", "piano"), ("fortepiano", "piano"),
    ("piano", "piano"), ("pno", "piano"), ("pf", "piano"),
    ("klavier", "piano"),  # German

    # ── Vocals ────────────────────────────────────────────────────
    # Choir (Italian = coro, French = choeur, German = chor)
    ("choir", "choir"), ("chorus", "choir"),
    ("coro", "choir"),  # Italian
    ("choeur", "choir"),  # French
    ("chor", "choir"),  # German
    ("voice", "choir"), ("vocal", "choir"), ("vocals", "choir"),
    ("soprano", "choir"), ("soprani", "choir"),
]


def _build_live_track_map(reaper_tracks: list[dict]) -> dict[str, str]:
    """Build a track_index→instrument_name map from REAPER's actual tracks.

    Prefers tracks WITH a VSTi instrument loaded over empty placeholder tracks.
    When multiple tracks match the same instrument name, the one with a VSTi wins.

    Args:
        reaper_tracks: List from get_track_instruments, each has
            {track_index, name, instrument, item_count}.

    Returns:
        Dict mapping str(track_index) → registry instrument name.
    """
    # First pass: collect all matches, noting which have VSTi
    matches = []  # (track_index_str, instrument_name, has_vsti)
    for t in reaper_tracks:
        ti = str(t["track_index"])
        combined = f"{t.get('name', '')} {t.get('instrument', '')}".lower()
        has_vsti = bool(t.get("instrument"))
        matched = None
        for keyword, reg_name in _INSTRUMENT_NAME_KEYWORDS:
            if keyword in combined:
                matched = reg_name
                break
        if matched:
            matches.append((ti, matched, has_vsti))

    # Second pass: for each instrument, prefer the track with VSTi
    # Build reverse map: instrument_name → best track index
    inst_best = {}  # instrument_name → (track_index_str, has_vsti)
    for ti, inst_name, has_vsti in matches:
        if inst_name not in inst_best:
            inst_best[inst_name] = (ti, has_vsti)
        else:
            existing_ti, existing_vsti = inst_best[inst_name]
            # Prefer VSTi track over non-VSTi
            if has_vsti and not existing_vsti:
                inst_best[inst_name] = (ti, has_vsti)

    # Build final map: track_index → instrument_name
    track_map = {}
    for inst_name, (ti, _) in inst_best.items():
        track_map[ti] = inst_name
    return track_map


# ============================================================
# Smart keyword maps for intent matching
# ============================================================

VALID_DYNAMICS = {"pp", "p", "mp", "mf", "f", "ff", "gentle_build",
                  "epic_build", "fade_out", "swell", "tension"}
VALID_RHYTHMS = {"sustained", "pulse_8ths", "pulse_16ths", "dotted_quarter",
                 "arpeggiated_up", "arpeggiated_down", "waltz", "tremolo",
                 "staccato_quarter", "syncopated", "building_8ths",
                 "melodic_neighbor", "bass_pedal", "slow_swell",
                 "pulsing_quarters", "desert_ostinato",
                 "building_quarters_to_8ths", "flowing_triplets", "marcato_hits"}
VALID_TEMPLATES = {"romantic_full", "action_epic", "intimate_chamber",
                   "suspense_building", "triumphant_finale"}
VALID_ROLES = {"melody", "countermelody", "bass_line", "harmonic_pad",
               "arpeggio", "rhythmic_drive", "doubling", "color", "tacet"}
VALID_VOICING_PARTS = {"violin_1", "violin_2", "viola", "cello", "bass"}

TEMPLATE_KEYWORDS = {
    "epic": "action_epic", "action": "action_epic", "zimmer": "action_epic",
    "dark": "action_epic", "batman": "action_epic", "war": "action_epic",
    "battle": "action_epic", "power": "action_epic", "intense": "action_epic",
    "romantic": "romantic_full", "williams": "romantic_full",
    "lush": "romantic_full", "beautiful": "romantic_full", "love": "romantic_full",
    "intimate": "intimate_chamber", "chamber": "intimate_chamber",
    "quiet": "intimate_chamber", "gentle": "intimate_chamber",
    "delicate": "intimate_chamber", "solo": "intimate_chamber",
    "suspense": "suspense_building", "tension": "suspense_building",
    "mystery": "suspense_building", "build": "suspense_building",
    "creepy": "suspense_building", "dark_ambient": "suspense_building",
    "triumph": "triumphant_finale", "finale": "triumphant_finale",
    "victory": "triumphant_finale", "grand": "triumphant_finale",
    "heroic": "triumphant_finale", "fanfare": "triumphant_finale",
}

ROLE_KEYWORDS = {
    "melody": "melody", "lead": "melody", "fanfare": "melody",
    "theme": "melody", "soar": "melody", "sing": "melody",
    "counter": "countermelody", "secondary": "countermelody",
    "response": "countermelody", "answer": "countermelody",
    "bass": "bass_line", "foundation": "bass_line", "anchor": "bass_line",
    "low": "bass_line", "pedal": "bass_line", "drone": "bass_line",
    "root": "bass_line", "deep": "bass_line", "sub": "bass_line",
    "pad": "harmonic_pad", "harmony": "harmonic_pad",
    "sustain": "harmonic_pad", "inner": "harmonic_pad",
    "warm": "harmonic_pad", "power": "harmonic_pad",
    "depth": "harmonic_pad", "swell": "harmonic_pad",
    "fill": "harmonic_pad", "texture": "harmonic_pad",
    "chord": "harmonic_pad", "stab": "harmonic_pad",
    "arpeg": "arpeggio", "shimmer": "arpeggio", "gliss": "arpeggio",
    "broken": "arpeggio", "harp": "arpeggio",
    "ostinato": "rhythmic_drive", "drive": "rhythmic_drive",
    "drum": "rhythmic_drive", "hit": "rhythmic_drive",
    "perc": "rhythmic_drive", "pulse": "rhythmic_drive",
    "march": "rhythmic_drive", "motor": "rhythmic_drive",
    "double": "doubling", "unison": "doubling", "reinforce": "doubling",
    "color": "color", "ornament": "color", "trill": "color",
    "sparkle": "color", "accent": "color", "grace": "color",
    "embellish": "color", "decor": "color",
    "tacet": "tacet", "silent": "tacet", "rest": "tacet",
}

RHYTHM_KEYWORDS = {
    "sustain": "sustained", "hold": "sustained", "whole": "sustained",
    "long": "sustained", "legato": "sustained", "pad": "sustained",
    "8th": "pulse_8ths", "eighth": "pulse_8ths",
    "16th": "pulse_16ths", "sixteenth": "pulse_16ths",
    "dotted": "dotted_quarter", "dot": "dotted_quarter",
    "arp": "arpeggiated_up", "arpeggiat": "arpeggiated_up",
    "waltz": "waltz", "triple": "waltz",
    "tremolo": "tremolo", "trem": "tremolo",
    "staccato": "staccato_quarter", "stacc": "staccato_quarter",
    "short": "staccato_quarter", "detach": "staccato_quarter",
    "synco": "syncopated", "offbeat": "syncopated",
    "build": "building_8ths", "intensif": "building_8ths",
    "grow": "building_8ths", "escala": "building_8ths",
    "neighbor": "melodic_neighbor", "ornament": "melodic_neighbor",
    "pedal": "bass_pedal", "drone": "bass_pedal",
    "swell": "slow_swell", "breath": "slow_swell",
    "pulse": "pulsing_quarters", "quarter": "pulsing_quarters",
    "ostinato": "desert_ostinato", "desert": "desert_ostinato",
    "repeat": "desert_ostinato", "motor": "desert_ostinato",
    "triplet": "flowing_triplets", "flow": "flowing_triplets",
    "marcato": "marcato_hits", "hit": "marcato_hits",
    "stab": "marcato_hits", "accent": "marcato_hits",
}

DYNAMICS_KEYWORDS = {
    "ppp": "pp", "pianissimo": "pp",
    "piano": "p", "soft": "p", "quiet": "p",
    "mezzo_piano": "mp", "medium_soft": "mp",
    "mezzo_forte": "mf", "medium": "mf", "moderate": "mf",
    "forte": "f", "loud": "f", "strong": "f",
    "fff": "ff", "fortissimo": "ff", "max": "ff", "full": "ff",
    "build": "epic_build", "epic": "epic_build", "crescendo": "epic_build",
    "gentle": "gentle_build", "gradual": "gentle_build",
    "fade": "fade_out", "decay": "fade_out", "dim": "fade_out",
    "swell": "swell", "wave": "swell",
    "tension": "tension", "suspense": "tension",
}


def match_keyword(value: str, keyword_map: dict, default: str) -> tuple[str, bool]:
    """Match an invalid value to the best valid one using keywords.
    Checks longer keywords first for better specificity.
    Returns (matched_value, was_converted)."""
    v_lower = value.lower().replace("-", "_").replace(" ", "_")
    # Sort by keyword length descending so "counter" matches before "lead"
    # and "ostinato" matches before "melody"
    for keyword, valid in sorted(keyword_map.items(),
                                 key=lambda kv: len(kv[0]), reverse=True):
        if keyword in v_lower:
            return valid, True
    return default, True
