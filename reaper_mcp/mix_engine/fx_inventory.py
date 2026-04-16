"""FX preference catalog — per-category ranked plugin substring matchers.

Matching is case-insensitive substring. Each list is ORDERED: the first
installed plugin that matches wins. REAPER stock is always at the bottom
as the universal fallback.

Rack-style plugins (StudioRack, PatchWork, Lion) hold plugins INSIDE them.
We detect their presence but don't try to configure modules nested inside —
REAPER's FX API treats rack interiors as opaque. If the user loads a rack,
we tell the AI about it so the AI can route around it (use standalone FX).

Preferences can be overridden per category by a user JSON file. See
`load_user_fx_preferences()` for the lookup order.
"""

from dataclasses import dataclass, field


# ────────────────────────────────────────────────────────────────
# Per-category preference lists
# Ordered highest quality → lowest. Case-insensitive substring match.
# Add a new plugin by inserting at the appropriate rank.
# ────────────────────────────────────────────────────────────────

EQ_RANKING = [
    # FabFilter tier (hand-calibrated in plugins.py)
    "FabFilter Pro-Q 3",
    "FabFilter Pro-Q 2",
    "FabFilter Pro-Q",
    # iZotope
    "iZotope Neutron 4",
    "iZotope Neutron 3",
    "iZotope Ozone 10 EQ",
    "iZotope Ozone 9 EQ",
    # Waves
    "F6 Floating-Band Dynamic EQ",   # Waves
    "F6",
    "H-EQ",
    "Renaissance Equalizer",
    "SSL E-Channel",
    "SSL G-Channel",
    "SSL G-Equalizer",
    "SSL E-Equalizer",
    "API 550",
    "API 560",
    "V-EQ4",
    "V-EQ3",
    "Q10 Equalizer",
    # Softube
    "Weiss EQ MP",
    "Weiss EQ1",
    "Tube-Tech ME 1B",
    # TDR
    "TDR Nova",
    "TDR SlickEQ",
    "TDR VOS SlickEQ",
    # Native Instruments Solid
    "Solid EQ",
    # Plugin Alliance
    "bx_digital V3",
    "Maag EQ4",
    "Mäag EQ4",
    "Pultec EQP-1A",
    "Millennia NSEQ-2",
    # Melda
    "MEqualizer",
    "MAutoEqualizer",
    # Tokyo Dawn free
    "TDR Nova GE",
    # REAPER stock (last)
    "ReaEQ",
]

COMPRESSOR_RANKING = [
    "FabFilter Pro-C 2",
    "FabFilter Pro-C",
    "FabFilter Pro-MB",
    # Waves SSL
    "SSL G-Master Buss Compressor",
    "SSL Compressor",
    "SSL E-Channel",             # has comp section
    "SSL G-Channel",
    # Waves 1176/LA2A emulations
    "CLA-76",
    "CLA-2A",
    "CLA-3A",
    "PuigChild 660",
    "PuigChild 670",
    "API 2500",
    "API-2500",
    "H-Comp",
    "Renaissance Compressor",
    "RCompressor",
    "C1 Compressor",
    "C6 Multiband",
    # iZotope
    "iZotope Neutron 4 Compressor",
    "iZotope Ozone 10 Dynamics",
    "Nectar 4",
    # Softube
    "FET Compressor",
    "Weiss DS1-MK3",
    "Tube-Tech CL 1B",
    "Drawmer 1973",
    "Drawmer S73",
    # Slate
    "FG-116",
    "FG-401",
    "FG-Grey",
    # Plugin Alliance
    "bx_opto",
    "SPL IRON",
    "Shadow Hills Mastering Compressor",
    # Klanghelm
    "MJUC",
    "DC8C",
    # TDR
    "TDR Kotelnikov",
    "TDR Molot",
    "TDR Limiter 6",
    # Native Instruments
    "VC 76",
    "VC 2A",
    "VC 160",
    "Solid Bus Comp",
    "Solid Dynamics",
    # Airwindows
    "Pressure4",
    "Pressure5",
    # Melda
    "MCompressor",
    "MDynamicsMB",
    # REAPER stock
    "ReaComp",
    "ReaXcomp",
]

LIMITER_RANKING = [
    "FabFilter Pro-L 2",
    "FabFilter Pro-L",
    # Waves
    "L1 Ultramaximizer",
    "L2 Ultramaximizer",
    "L3 Multimaximizer",
    "L3-LL Multimaximizer",
    "L3-16 Multimaximizer",
    "WLM Plus",
    # iZotope
    "Ozone 10 Maximizer",
    "Ozone 9 Maximizer",
    # Softube
    "Weiss MM-1",
    "Weiss DS1-MK3",
    # Slate
    "FG-X",
    "FG-X 2",
    # Invisible Limiter
    "Invisible Limiter",
    # Free
    "LoudMax",
    "Limiter No6",
    "Youlean Loudness Meter",
    # TDR
    "TDR Limiter 6",
    "Limiter 6",
    # REAPER stock
    "ReaLimit",
    "JS: Limiter",
]

REVERB_RANKING = [
    "FabFilter Pro-R",
    # Valhalla (fan favorites — often preferred over FabFilter for character)
    "Valhalla VintageVerb",
    "Valhalla Plate",
    "Valhalla Room",
    "Valhalla Shimmer",
    "Valhalla Supermassive",
    "ValhallaDelay",
    # Liquidsonics
    "Cinematic Rooms",
    "Seventh Heaven",
    "Reverberate",
    # Waves
    "H-Reverb",
    "R-Verb",
    "TrueVerb",
    "IR1",
    "Renaissance Reverb",
    "Abbey Road Reverb Plates",
    # Lexicon emulations / Waves
    "PCM Native Reverb",
    "224",
    "480L",
    # UAD-style
    "EMT 140",
    "EMT 250",
    "AKG BX 20",
    # Eventide
    "Blackhole",
    "UltraReverb",
    # Melda
    "MConvolutionEZ",
    "MReverb",
    # 2CAudio
    "B2",
    "Breeze 2",
    # Baby Audio
    "Crystalline",
    "Comeback Kid",
    # Native Instruments
    "Raum",
    "Replika",
    # REAPER stock
    "ReaVerbate",
    "ReaVerb",
]

DEESSER_RANKING = [
    "FabFilter Pro-DS",
    "DeEsser",                # Waves DeEsser
    "Sibilance",              # Waves
    "Nectar 4 De-Esser",
    "bx_refinement",
    "oeksound soothe2",
    "soothe2",
    "Renaissance DeEsser",
    "SieQ",
    # JS
    "JS: DeEsser",
]

GATE_RANKING = [
    "FabFilter Pro-G",
    "C1 Gate",                # Waves
    "NS1 Noise Suppressor",   # Waves
    "Smack Attack",           # Waves (transient, but often used as gate-ish)
    "Drawmer DS201",
    "ReaGate",
]

SATURATOR_RANKING = [
    "FabFilter Saturn 2",
    "FabFilter Saturn",
    "Decapitator",            # Soundtoys
    "Radiator",               # Soundtoys
    "Little AlterBoy",
    "Kramer Master Tape",     # Waves
    "J37",                    # Waves tape
    "Abbey Road J37",
    "Tape",                   # Softube
    "Saturation Knob",        # Softube (free)
    "Harmonic Maximizer",
    "SDRR",                   # Klanghelm
    "IVGI",                   # Klanghelm (free)
    "FG-Stress",
    "Virtual Console Collection",
    # Airwindows (many, all free)
    "Density",
    "Ultrasonic",
    "Console7Channel",
    # NI
    "Transient Master",
]

MULTIBAND_RANKING = [
    "FabFilter Pro-MB",
    "FabFilter Pro-C 2",       # has MB mode
    "C6 Multiband",            # Waves
    "C4 Multiband",
    "iZotope Neutron 4 Compressor",  # can multiband
    "Ozone 10 Dynamics",
    "MDynamicsMB",             # Melda
    "bx_XL V2",
    "ReaXcomp",
]

STEREO_RANKING = [
    "FabFilter Pro-Q 3",       # stereo ops via M/S per band
    "bx_solo",
    "bx_stereomaker",
    "Waves S1 Stereo Imager",
    "Ozone 10 Imager",
    "MStereoExpander",
    "JS: Stereo Enhancer",     # REAPER stock JS
]


# ────────────────────────────────────────────────────────────────
# Rack-style plugins — detected, but NOT configured inside.
# If any of these are on a track, setup_fx_chain's fuzzy param matching
# won't reach modules nested inside the rack.
# ────────────────────────────────────────────────────────────────

RACK_PLUGINS = [
    "Waves StudioRack",
    "StudioRack",
    "Blue Cat's PatchWork",
    "PatchWork",
    "Blue Cat's MB-7 Mixer",
    "MB-7 Mixer",
    "Unfiltered Audio Lion",
    "Lion",
    "Kilohearts Multipass",
    "Multipass",
    "Kilohearts Snap Heap",
    "Snap Heap",
    "MeldaProduction MXXX",
    "MXXX",
    "BlueCat's ReGuitar",
]


# ────────────────────────────────────────────────────────────────
# Category map — single source of truth for lookups
# ────────────────────────────────────────────────────────────────

CATEGORY_RANKINGS = {
    "eq":           EQ_RANKING,
    "compressor":   COMPRESSOR_RANKING,
    "limiter":      LIMITER_RANKING,
    "reverb":       REVERB_RANKING,
    "deesser":      DEESSER_RANKING,
    "gate":         GATE_RANKING,
    "saturator":    SATURATOR_RANKING,
    "multiband":    MULTIBAND_RANKING,
    "stereo":       STEREO_RANKING,
}


# ────────────────────────────────────────────────────────────────
# Matching helpers
# ────────────────────────────────────────────────────────────────

def _match(installed_names: list[str], preferences: list[str]) -> str | None:
    """Return the best installed plugin for the ranked preference list, or None."""
    low = [n.lower() for n in installed_names]
    for pref in preferences:
        pref_low = pref.lower()
        for orig, lo in zip(installed_names, low):
            if pref_low in lo:
                return orig
    return None


def best_for_category(category: str, installed_names: list[str]) -> str | None:
    ranking = CATEGORY_RANKINGS.get(category)
    if ranking is None:
        return None
    return _match(installed_names, ranking)


def detect_racks(installed_names: list[str]) -> list[str]:
    found: list[str] = []
    low = [n.lower() for n in installed_names]
    for rack in RACK_PLUGINS:
        rl = rack.lower()
        for orig, lo in zip(installed_names, low):
            if rl in lo and orig not in found:
                found.append(orig)
                break
    return found
