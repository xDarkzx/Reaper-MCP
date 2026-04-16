"""CC mapping layer — translates source MIDI CC data to target VSTi CC scheme.

Reference MIDIs come from various sources (Cinematic Studio, MuseScore, generic GM)
each using different CC assignments for dynamics, articulation, etc.
This module normalizes them all to a common scheme, then maps to the target VSTi
(default: BBC Spitfire).

Source detection is automatic based on which CCs are present in the data.

Usage:
    from reaper_mcp.cc_map import map_ccs_to_target
    mapped = map_ccs_to_target(raw_ccs, instrument="violin_1")
"""

# ============================================================
# Source VSTi CC schemes (what the reference MIDIs use)
# ============================================================

# Cinematic Studio Strings/Woodwinds/Brass (CSS/CSW/CSB)
# CC58 articulation values → articulation names
_CSS_CC58_STRINGS = {
    5: "legato",
    10: "spiccato",
    15: "long",
    20: "legato",
    25: "tremolo",
    30: "tremolo",
    56: "pizzicato",
    60: "pizzicato",
    65: "tremolo",
    70: "staccato",
    75: "legato",
}

_CSS_CC58_WOODWINDS = {
    1: "legato",
    7: "legato",
    12: "long",
    17: "staccato",
    22: "staccatissimo",
    27: "sfz",
    47: "long",      # sustained variant
    67: "legato",
    72: "legato",
}

_CSS_CC58_BRASS = {
    1: "legato",
    12: "long",
    17: "staccato",
    22: "staccatissimo",
    26: "marcato",
    67: "legato",
    72: "legato",
}

# ============================================================
# Target VSTi CC schemes (what we output)
# ============================================================

# BBC Spitfire official CC map (from Spitfire Audio documentation):
#   CC1  = Dynamics (crossfades between pp/mf/ff sample layers)
#   CC7  = Volume (plugin level)
#   CC10 = Pan
#   CC11 = Expression (secondary volume — NOT dynamic layer switching)
#   CC16 = Speed / Tightness (legato intervals)
#   CC17 = Release time
#   CC18 = Tightness (short notes)
#   CC19 = Reverb amount (Spitfire plugin only — NOT dynamics!)
#   CC21 = Vibrato
#   CC22-27 = Microphone signals (library-specific)
#   CC64 = Sustain pedal

# Source CC → Target CC mapping
_DYNAMICS_CC_MAP = {
    # CC2 (breath controller) is the primary dynamics in most reference MIDIs
    # → map to CC1 (Spitfire dynamics = sample layer crossfade)
    2: 1,
    # CC1 stays CC1 (already correct for Spitfire)
    1: 1,
    # CC11 stays CC11 (expression/volume)
    11: 11,
    # CC7 stays CC7 (volume)
    7: 7,
}

# CCs that pass through unchanged to target
_PASSTHROUGH_CCS = {
    64,  # sustain pedal
    10,  # pan
}

# CCs containing articulation data (decoded separately, not passed through)
_ARTICULATION_CCS = {
    58,  # Cinematic Studio articulation switching
    32,  # UACC (Universal Articulation Controller)
}

# CCs that are DAW/mixer effects — strip from output
_MIXING_CCS = {
    91,  # reverb send (GM standard — not Spitfire reverb which is CC19)
    93,  # chorus send
}

# Cinematic Studio custom CCs (section size, vibrato, etc.)
_CSS_CUSTOM_CCS = {116, 117, 118, 119}


# ============================================================
# Source detection
# ============================================================

def detect_source_type(ccs: list[dict]) -> str:
    """Detect which VSTi/source the CC data comes from.

    Returns: "cinematic_studio", "generic_breath", "generic_mod", or "minimal"
    """
    cc_numbers = {cc.get("cc", cc.get("cc_number", 0)) for cc in ccs}

    if 58 in cc_numbers:
        return "cinematic_studio"
    if 2 in cc_numbers and 1 not in cc_numbers:
        return "generic_breath"
    if 1 in cc_numbers:
        return "generic_mod"
    return "minimal"


# ============================================================
# Articulation extraction from CC data
# ============================================================

def extract_articulations_from_ccs(ccs: list[dict], instrument: str,
                                    family: str | None = None) -> list[tuple[float, str]]:
    """Extract articulation changes from CC data.

    Returns list of (beat_position, articulation_name) sorted by time.
    """
    # Determine instrument family for CC58 mapping
    if family is None:
        if instrument in {"violin_1", "violin_2", "viola", "cello", "bass"}:
            family = "strings"
        elif instrument in {"trumpet", "french_horn", "trombone", "tuba"}:
            family = "brass"
        elif instrument in {"flute", "piccolo", "oboe", "clarinet", "bassoon"}:
            family = "woodwinds"

    cc58_map = {
        "strings": _CSS_CC58_STRINGS,
        "brass": _CSS_CC58_BRASS,
        "woodwinds": _CSS_CC58_WOODWINDS,
    }.get(family, _CSS_CC58_WOODWINDS)

    articulations = []
    for cc in ccs:
        cc_num = cc.get("cc", cc.get("cc_number", 0))
        if cc_num == 58:
            value = cc.get("value", cc.get("cc_value", 0))
            artic = cc58_map.get(value)
            if artic:
                beat = cc.get("beat", cc.get("position", 0))
                articulations.append((beat, artic))

    articulations.sort(key=lambda a: a[0])
    return articulations


# ============================================================
# Main CC mapping
# ============================================================

def map_ccs_to_target(ccs: list[dict], instrument: str = "",
                       target: str = "bbc_spitfire") -> list[dict]:
    """Map source CC data to target VSTi CC scheme.

    Handles:
    - CC2 (breath) → CC1 (modwheel) for BBC Spitfire
    - Strips mixing/setup CCs (reverb, chorus)
    - Strips articulation CCs (handled separately via keyswitches)
    - Passes through sustain pedal, pan
    - Strips CSS custom CCs (116-119)

    Args:
        ccs: Raw CC list from score block. Each has {cc, value, beat} or
             {cc_number, cc_value, position}.
        instrument: Instrument name (for context).
        target: Target VSTi scheme (currently only "bbc_spitfire").

    Returns:
        Mapped CC list in output format {cc_number, cc_value, position, channel}.
    """
    result = []

    for cc in ccs:
        # Normalize field names (blocks use "cc"/"beat", output uses "cc_number"/"position")
        cc_num = cc.get("cc", cc.get("cc_number", 0))
        cc_val = cc.get("value", cc.get("cc_value", 0))
        position = cc.get("beat", cc.get("position", 0))
        channel = cc.get("channel", 0)

        # Skip mixing CCs
        if cc_num in _MIXING_CCS:
            continue

        # Skip articulation CCs (handled via keyswitches)
        if cc_num in _ARTICULATION_CCS:
            continue

        # Skip CSS custom CCs
        if cc_num in _CSS_CUSTOM_CCS:
            continue

        # Map dynamics CCs
        if cc_num in _DYNAMICS_CC_MAP:
            target_cc = _DYNAMICS_CC_MAP[cc_num]
            result.append({
                "cc_number": target_cc,
                "cc_value": max(0, min(127, cc_val)),
                "position": round(position, 3),
                "channel": channel,
            })
            continue

        # Pass through sustain, pan, etc.
        if cc_num in _PASSTHROUGH_CCS:
            result.append({
                "cc_number": cc_num,
                "cc_value": max(0, min(127, cc_val)),
                "position": round(position, 3),
                "channel": channel,
            })
            continue

        # Any other CC — pass through as-is (don't throw away data)
        result.append({
            "cc_number": cc_num,
            "cc_value": max(0, min(127, cc_val)),
            "position": round(position, 3),
            "channel": channel,
        })

    return result
