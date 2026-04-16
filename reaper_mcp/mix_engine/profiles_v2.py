"""Style profile schema v2 — rock, pop, EDM, and EDM sub-genres.

Each style defines:
  - Instrument role EQ + compression (per-role, not per-specific-instrument)
  - Sidechain relationships (source → target pumping)
  - Mastering target (LUFS, true peak, stereo width, limiter character)
  - Reverb bus setup
  - Track-name aliases so live REAPER tracks map to roles

Instrument roles are abstract — "kick", "sub_bass", "lead_synth" — resolved
against live track names via aliases (case-insensitive substring match).

All 25 styles share the same schema; data lives in STYLE_PROFILES.
Orchestral genres continue to use the legacy `profiles.py` path.
"""

from dataclasses import dataclass, field
from typing import Optional


# ────────────────────────────────────────────────────────────────
# Schema dataclasses
# ────────────────────────────────────────────────────────────────

@dataclass
class EQBand:
    freq: float
    gain_db: float
    q: float = 1.0
    shape: str = "bell"  # bell | low_shelf | high_shelf | low_cut | high_cut


@dataclass
class EQProfile:
    hp_freq: float = 20.0
    bands: list[EQBand] = field(default_factory=list)

    def to_legacy_dict(self) -> dict:
        """Convert to the shape that plugins.py expects (cuts + boosts)."""
        cuts = []
        boosts = []
        for b in self.bands:
            entry = {"freq": b.freq, "gain_db": b.gain_db, "q": b.q, "shape": b.shape}
            if b.gain_db < 0:
                cuts.append(entry)
            else:
                boosts.append(entry)
        return {"hp_freq": self.hp_freq, "cuts": cuts, "boosts": boosts}


@dataclass
class CompProfile:
    threshold_db: float = -18.0
    ratio: float = 2.0
    attack_ms: float = 20.0
    release_ms: float = 150.0
    makeup_db: float = 2.0
    knee_db: float = 6.0

    def to_dict(self) -> dict:
        return {
            "threshold_db": self.threshold_db, "ratio": self.ratio,
            "attack_ms": self.attack_ms, "release_ms": self.release_ms,
            "makeup_db": self.makeup_db, "knee_db": self.knee_db,
        }


@dataclass
class ReverbSend:
    bus: str       # "hall" | "room" | "plate" | custom bus name
    send_db: float


@dataclass
class InstrumentRole:
    eq: EQProfile
    comp: Optional[CompProfile] = None
    volume_db: float = 0.0
    pan: float = 0.0
    sends: list[ReverbSend] = field(default_factory=list)


@dataclass
class SidechainSpec:
    """A kick→pad or kick→bass pumping relationship.

    amount: 0-1 — how aggressive the pumping. Translated to threshold + ratio.
    attack_ms / release_ms: compressor envelope; fast attack + medium release = pump.
    """
    source: str   # role name that triggers the duck
    target: str   # role name that gets ducked
    amount: float = 0.7
    attack_ms: float = 5.0
    release_ms: float = 180.0
    ratio: float = 8.0
    threshold_db: float = -20.0


@dataclass
class ReverbBus:
    room_size: float = 0.5
    dampening: float = 0.5
    wet_db: float = -6.0
    lowpass_hz: float = 12000
    hipass_hz: float = 100
    width: float = 1.0
    color: tuple[int, int, int] = (120, 120, 140)

    def to_dict(self) -> dict:
        return {
            "room_size": self.room_size, "dampening": self.dampening,
            "wet_db": self.wet_db, "lowpass_hz": self.lowpass_hz,
            "hipass_hz": self.hipass_hz, "width": self.width,
            "color": list(self.color),
        }


@dataclass
class MasteringChain:
    target_lufs: float = -14.0        # Spotify / YT default
    true_peak_db: float = -1.0        # Broadcast-safe ceiling
    stereo_width: float = 1.0         # 1.0 neutral, >1 wider, <1 narrower
    limiter_character: str = "transparent"  # transparent | punchy | aggressive | warm
    # Final tonal shaping on master bus
    low_shelf_db: float = 0.0
    low_shelf_freq: float = 80.0
    high_shelf_db: float = 0.0
    high_shelf_freq: float = 12000.0
    # Optional gentle bus compression before the limiter
    bus_comp: Optional[CompProfile] = None
    # Optional surgical cuts on master bus
    bus_cuts: list[EQBand] = field(default_factory=list)


@dataclass
class StyleProfile:
    name: str
    family: str                         # "rock" | "pop" | "edm" | "electronic"
    bpm_range: tuple[int, int]
    key_hints: list[str] = field(default_factory=list)  # informational

    instrument_roles: dict[str, InstrumentRole] = field(default_factory=dict)

    # Track-name aliases — lowercase substring match against REAPER track name.
    # Multiple aliases per role; first match wins.
    # e.g. {"kick": ["kick", "bd", "bassdrum"], "lead_synth": ["lead", "synth lead"]}
    aliases: dict[str, list[str]] = field(default_factory=dict)

    sidechain: list[SidechainSpec] = field(default_factory=list)
    reverb_buses: dict[str, ReverbBus] = field(default_factory=dict)
    bus_sends: dict[str, dict[str, float]] = field(default_factory=dict)
    # bus_sends: {bus_name: {role_name: send_db}}

    mastering: MasteringChain = field(default_factory=MasteringChain)
    structure_hints: list[str] = field(default_factory=list)


# ────────────────────────────────────────────────────────────────
# Default reverb buses — used unless a style overrides
# ────────────────────────────────────────────────────────────────

DEFAULT_REVERB_BUSES = {
    "hall": ReverbBus(
        room_size=0.75, dampening=0.35, wet_db=-8.0,
        lowpass_hz=12000, hipass_hz=100, width=1.0, color=(70, 130, 200),
    ),
    "room": ReverbBus(
        room_size=0.45, dampening=0.50, wet_db=-6.0,
        lowpass_hz=10000, hipass_hz=150, width=0.8, color=(70, 180, 70),
    ),
    "plate": ReverbBus(
        room_size=0.55, dampening=0.25, wet_db=-7.0,
        lowpass_hz=14000, hipass_hz=200, width=1.0, color=(160, 70, 180),
    ),
}


# ────────────────────────────────────────────────────────────────
# Style catalog — populated by genre-family modules
# ────────────────────────────────────────────────────────────────

STYLE_PROFILES: dict[str, StyleProfile] = {}


def register_profile(profile: StyleProfile) -> None:
    STYLE_PROFILES[profile.name] = profile


def get_profile(name: str) -> Optional[StyleProfile]:
    return STYLE_PROFILES.get(name)


def list_profiles(family: Optional[str] = None) -> list[str]:
    if family is None:
        return sorted(STYLE_PROFILES.keys())
    return sorted(n for n, p in STYLE_PROFILES.items() if p.family == family)


# ────────────────────────────────────────────────────────────────
# Helpers to resolve live track_map → role_map using aliases
# ────────────────────────────────────────────────────────────────

def resolve_roles(profile: StyleProfile, live_tracks: list[dict]) -> dict[int, str]:
    """Map REAPER track index → role name using the profile's aliases.

    live_tracks: list of {"index": int, "name": str} from track_get_all.

    Matching: LONGEST matching alias wins. This means "Vocal Chop" resolves
    to role `vocal_chop` (alias "vocal chop", len=10) rather than `vocal_lead`
    (alias "vocal", len=5), even though both would match as substrings.
    """
    role_map: dict[int, str] = {}
    for track in live_tracks:
        name = (track.get("name") or "").lower()
        if not name:
            continue
        best_role: Optional[str] = None
        best_alias_len = -1
        for role, alias_list in profile.aliases.items():
            for alias in alias_list:
                a = alias.lower()
                if a and a in name and len(a) > best_alias_len:
                    best_role = role
                    best_alias_len = len(a)
        if best_role is not None:
            role_map[int(track["index"])] = best_role
    return role_map


# ────────────────────────────────────────────────────────────────
# Sidechain amount → compressor settings
# ────────────────────────────────────────────────────────────────

def sidechain_amount_to_comp(spec: SidechainSpec) -> CompProfile:
    """Translate a SidechainSpec's amount to ReaComp-compatible settings.

    Higher amount → lower threshold, higher ratio = more pumping.
    """
    # amount 0.0 → threshold -10, ratio 2  (subtle)
    # amount 1.0 → threshold -30, ratio 12 (aggressive)
    amt = max(0.0, min(1.0, spec.amount))
    thresh = -10.0 - amt * 20.0  # -10 .. -30 dB
    ratio = 2.0 + amt * 10.0     # 2 .. 12
    return CompProfile(
        threshold_db=spec.threshold_db if spec.threshold_db != -20.0 else thresh,
        ratio=spec.ratio if spec.ratio != 8.0 else ratio,
        attack_ms=spec.attack_ms,
        release_ms=spec.release_ms,
        makeup_db=0.0,    # no makeup on sidechain comp
        knee_db=2.0,      # hard knee for pumping
    )
