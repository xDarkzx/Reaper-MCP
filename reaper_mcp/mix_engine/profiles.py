"""Mix profiles — per-instrument volume, EQ, compression, reverb, and routing presets."""

# ────────────────────────────────────────────────────────────────
# Volume staging (dB offsets from unity)
# ────────────────────────────────────────────────────────────────
VOLUME_STAGING = {
    "violin_1":         0.0,
    "violin_2":        -1.5,
    "viola":           -2.0,
    "cello":           -1.0,
    "bass":            -3.0,
    "piccolo":         -5.0,
    "flute":           -3.0,
    "oboe":            -3.5,
    "clarinet":        -3.0,
    "bassoon":         -3.5,
    "french_horn":     -2.0,
    "trumpet":         -4.0,
    "trombone":        -4.0,
    "tuba":            -4.5,
    "harp":            -5.0,
    "timpani":         -2.0,
    "tuned_percussion": -4.0,
    "choir":           -3.0,
    "piano":           -4.0,
    "hz_taiko":        -3.0,
    "hz_lo_taiko":     -3.0,
    "hz_boobams":      -5.0,
}

# ────────────────────────────────────────────────────────────────
# EQ profiles — per-instrument
# Each has: hp_freq (high-pass cutoff Hz), cuts, boosts
# Band shapes: "bell" (default), "high_shelf", "low_shelf"
# ────────────────────────────────────────────────────────────────
EQ_PROFILES = {
    "violin_1": {
        "hp_freq": 80,
        "cuts": [{"freq": 800, "gain_db": -2.0, "q": 1.0}],
        "boosts": [
            {"freq": 3000, "gain_db": 1.5, "q": 1.0},
            {"freq": 12000, "gain_db": 1.5, "q": 0.8, "shape": "high_shelf"},
        ],
    },
    "violin_2": {
        "hp_freq": 80,
        "cuts": [{"freq": 800, "gain_db": -1.5, "q": 1.0}],
        "boosts": [
            {"freq": 2500, "gain_db": 1.0, "q": 1.0},
            {"freq": 10000, "gain_db": 1.0, "q": 0.8, "shape": "high_shelf"},
        ],
    },
    "viola": {
        "hp_freq": 60,
        "cuts": [{"freq": 600, "gain_db": -1.5, "q": 1.0}],
        "boosts": [
            {"freq": 2000, "gain_db": 1.0, "q": 1.0},
            {"freq": 8000, "gain_db": 1.0, "q": 0.8, "shape": "high_shelf"},
        ],
    },
    "cello": {
        "hp_freq": 40,
        "cuts": [{"freq": 400, "gain_db": -1.5, "q": 1.0}],
        "boosts": [
            {"freq": 1500, "gain_db": 1.0, "q": 1.0},
            {"freq": 6000, "gain_db": 1.0, "q": 0.8, "shape": "high_shelf"},
        ],
    },
    "bass": {
        "hp_freq": 30,
        "cuts": [{"freq": 300, "gain_db": -2.0, "q": 1.0}],
        "boosts": [
            {"freq": 80, "gain_db": 1.5, "q": 0.8, "shape": "low_shelf"},
            {"freq": 2500, "gain_db": 1.0, "q": 1.0},
        ],
    },
    "piccolo": {
        "hp_freq": 200,
        "cuts": [{"freq": 2000, "gain_db": -2.0, "q": 1.5}],
        "boosts": [
            {"freq": 5000, "gain_db": 1.0, "q": 1.0},
        ],
    },
    "flute": {
        "hp_freq": 150,
        "cuts": [{"freq": 1200, "gain_db": -1.5, "q": 1.0}],
        "boosts": [
            {"freq": 4000, "gain_db": 1.5, "q": 1.0},
            {"freq": 12000, "gain_db": 1.0, "q": 0.8, "shape": "high_shelf"},
        ],
    },
    "oboe": {
        "hp_freq": 150,
        "cuts": [{"freq": 1000, "gain_db": -2.0, "q": 1.5}],
        "boosts": [
            {"freq": 3500, "gain_db": 1.0, "q": 1.0},
        ],
    },
    "clarinet": {
        "hp_freq": 100,
        "cuts": [{"freq": 800, "gain_db": -1.5, "q": 1.0}],
        "boosts": [
            {"freq": 2500, "gain_db": 1.0, "q": 1.0},
            {"freq": 10000, "gain_db": 1.0, "q": 0.8, "shape": "high_shelf"},
        ],
    },
    "bassoon": {
        "hp_freq": 50,
        "cuts": [{"freq": 500, "gain_db": -1.5, "q": 1.0}],
        "boosts": [
            {"freq": 1500, "gain_db": 1.0, "q": 1.0},
        ],
    },
    "french_horn": {
        "hp_freq": 60,
        "cuts": [{"freq": 500, "gain_db": -1.5, "q": 1.0}],
        "boosts": [
            {"freq": 2000, "gain_db": 1.5, "q": 1.0},
            {"freq": 8000, "gain_db": 1.0, "q": 0.8, "shape": "high_shelf"},
        ],
    },
    "trumpet": {
        "hp_freq": 100,
        "cuts": [{"freq": 800, "gain_db": -2.0, "q": 1.5}],
        "boosts": [
            {"freq": 3000, "gain_db": 1.5, "q": 1.0},
            {"freq": 10000, "gain_db": 1.0, "q": 0.8, "shape": "high_shelf"},
        ],
    },
    "trombone": {
        "hp_freq": 50,
        "cuts": [{"freq": 500, "gain_db": -1.5, "q": 1.0}],
        "boosts": [
            {"freq": 2000, "gain_db": 1.5, "q": 1.0},
        ],
    },
    "tuba": {
        "hp_freq": 30,
        "cuts": [{"freq": 300, "gain_db": -2.0, "q": 1.0}],
        "boosts": [
            {"freq": 100, "gain_db": 1.0, "q": 0.8, "shape": "low_shelf"},
            {"freq": 1500, "gain_db": 1.0, "q": 1.0},
        ],
    },
    "harp": {
        "hp_freq": 40,
        "cuts": [{"freq": 400, "gain_db": -1.5, "q": 1.0}],
        "boosts": [
            {"freq": 2500, "gain_db": 1.5, "q": 1.0},
            {"freq": 10000, "gain_db": 1.5, "q": 0.8, "shape": "high_shelf"},
        ],
    },
    "timpani": {
        "hp_freq": 30,
        "cuts": [{"freq": 400, "gain_db": -2.0, "q": 1.5}],
        "boosts": [
            {"freq": 80, "gain_db": 2.0, "q": 0.8, "shape": "low_shelf"},
            {"freq": 3000, "gain_db": 1.5, "q": 1.0},
        ],
    },
    "tuned_percussion": {
        "hp_freq": 100,
        "cuts": [{"freq": 800, "gain_db": -1.5, "q": 1.0}],
        "boosts": [
            {"freq": 4000, "gain_db": 1.5, "q": 1.0},
            {"freq": 12000, "gain_db": 1.5, "q": 0.8, "shape": "high_shelf"},
        ],
    },
    "choir": {
        "hp_freq": 80,
        "cuts": [{"freq": 600, "gain_db": -1.5, "q": 1.0}],
        "boosts": [
            {"freq": 2500, "gain_db": 1.5, "q": 1.0},
            {"freq": 10000, "gain_db": 1.0, "q": 0.8, "shape": "high_shelf"},
        ],
    },
    "piano": {
        "hp_freq": 40,
        "cuts": [{"freq": 400, "gain_db": -1.5, "q": 1.0}],
        "boosts": [
            {"freq": 3000, "gain_db": 1.5, "q": 1.0},
            {"freq": 10000, "gain_db": 1.0, "q": 0.8, "shape": "high_shelf"},
        ],
    },
}

# ────────────────────────────────────────────────────────────────
# Compression profiles — per instrument family
# threshold_db: where compression kicks in (lower = more compression)
# ratio: compression ratio (2.0 = gentle, 4.0 = moderate)
# attack_ms: how fast the compressor reacts (slow = preserve transients)
# release_ms: how fast it lets go
# makeup_db: gain added after compression to restore level
# knee_db: soft knee width (0 = hard, 6+ = soft)
# ────────────────────────────────────────────────────────────────
COMPRESSION_PROFILES = {
    "violin_1": {
        "threshold_db": -18.0, "ratio": 2.0,
        "attack_ms": 30.0, "release_ms": 150.0,
        "makeup_db": 2.0, "knee_db": 6.0,
    },
    "violin_2": {
        "threshold_db": -18.0, "ratio": 2.0,
        "attack_ms": 30.0, "release_ms": 150.0,
        "makeup_db": 2.0, "knee_db": 6.0,
    },
    "viola": {
        "threshold_db": -18.0, "ratio": 2.0,
        "attack_ms": 25.0, "release_ms": 150.0,
        "makeup_db": 2.0, "knee_db": 6.0,
    },
    "cello": {
        "threshold_db": -16.0, "ratio": 2.5,
        "attack_ms": 20.0, "release_ms": 180.0,
        "makeup_db": 2.5, "knee_db": 6.0,
    },
    "bass": {
        "threshold_db": -16.0, "ratio": 3.0,
        "attack_ms": 15.0, "release_ms": 200.0,
        "makeup_db": 3.0, "knee_db": 4.0,
    },
    "french_horn": {
        "threshold_db": -14.0, "ratio": 3.0,
        "attack_ms": 15.0, "release_ms": 120.0,
        "makeup_db": 3.0, "knee_db": 4.0,
    },
    "trumpet": {
        "threshold_db": -12.0, "ratio": 3.5,
        "attack_ms": 10.0, "release_ms": 100.0,
        "makeup_db": 3.0, "knee_db": 3.0,
    },
    "trombone": {
        "threshold_db": -14.0, "ratio": 3.0,
        "attack_ms": 12.0, "release_ms": 120.0,
        "makeup_db": 3.0, "knee_db": 4.0,
    },
    "tuba": {
        "threshold_db": -16.0, "ratio": 3.0,
        "attack_ms": 15.0, "release_ms": 150.0,
        "makeup_db": 2.5, "knee_db": 4.0,
    },
    "flute": {
        "threshold_db": -20.0, "ratio": 1.8,
        "attack_ms": 30.0, "release_ms": 150.0,
        "makeup_db": 1.5, "knee_db": 8.0,
    },
    "oboe": {
        "threshold_db": -20.0, "ratio": 1.8,
        "attack_ms": 30.0, "release_ms": 150.0,
        "makeup_db": 1.5, "knee_db": 8.0,
    },
    "clarinet": {
        "threshold_db": -20.0, "ratio": 1.8,
        "attack_ms": 30.0, "release_ms": 150.0,
        "makeup_db": 1.5, "knee_db": 8.0,
    },
    "bassoon": {
        "threshold_db": -18.0, "ratio": 2.0,
        "attack_ms": 25.0, "release_ms": 150.0,
        "makeup_db": 2.0, "knee_db": 6.0,
    },
    "piccolo": {
        "threshold_db": -20.0, "ratio": 1.8,
        "attack_ms": 30.0, "release_ms": 150.0,
        "makeup_db": 1.5, "knee_db": 8.0,
    },
    "timpani": {
        "threshold_db": -12.0, "ratio": 3.5,
        "attack_ms": 8.0, "release_ms": 200.0,
        "makeup_db": 3.0, "knee_db": 3.0,
    },
    "tuned_percussion": {
        "threshold_db": -14.0, "ratio": 3.0,
        "attack_ms": 10.0, "release_ms": 150.0,
        "makeup_db": 2.5, "knee_db": 4.0,
    },
    "harp": {
        "threshold_db": -18.0, "ratio": 2.0,
        "attack_ms": 15.0, "release_ms": 150.0,
        "makeup_db": 2.0, "knee_db": 6.0,
    },
    "piano": {
        "threshold_db": -16.0, "ratio": 2.5,
        "attack_ms": 12.0, "release_ms": 150.0,
        "makeup_db": 2.5, "knee_db": 6.0,
    },
    "choir": {
        "threshold_db": -16.0, "ratio": 2.5,
        "attack_ms": 20.0, "release_ms": 150.0,
        "makeup_db": 2.0, "knee_db": 6.0,
    },
    "hz_taiko": {
        "threshold_db": -10.0, "ratio": 4.0,
        "attack_ms": 5.0, "release_ms": 250.0,
        "makeup_db": 4.0, "knee_db": 3.0,
    },
    "hz_lo_taiko": {
        "threshold_db": -10.0, "ratio": 4.0,
        "attack_ms": 5.0, "release_ms": 250.0,
        "makeup_db": 4.0, "knee_db": 3.0,
    },
    "hz_boobams": {
        "threshold_db": -12.0, "ratio": 3.5,
        "attack_ms": 8.0, "release_ms": 200.0,
        "makeup_db": 3.0, "knee_db": 3.0,
    },
}

# ────────────────────────────────────────────────────────────────
# Reverb bus configurations
# ────────────────────────────────────────────────────────────────
REVERB_BUSES = {
    "hall": {
        "room_size": 0.75,       # large hall
        "dampening": 0.35,       # moderate high-freq absorption
        "wet_db": -8.0,
        "lowpass_hz": 12000,
        "hipass_hz": 100,
        "width": 1.0,
        "color": [70, 130, 200],  # steel blue
    },
    "room": {
        "room_size": 0.45,       # medium room
        "dampening": 0.50,       # more dampened
        "wet_db": -6.0,
        "lowpass_hz": 10000,
        "hipass_hz": 150,
        "width": 0.8,
        "color": [70, 180, 70],   # green
    },
    "plate": {
        "room_size": 0.55,       # plate-like
        "dampening": 0.25,       # bright
        "wet_db": -7.0,
        "lowpass_hz": 14000,
        "hipass_hz": 200,
        "width": 1.0,
        "color": [160, 70, 180],  # purple
    },
}

# ────────────────────────────────────────────────────────────────
# Instrument → family mapping for send routing
# ────────────────────────────────────────────────────────────────
INSTRUMENT_FAMILIES = {
    "violin_1": "strings", "violin_2": "strings", "viola": "strings",
    "cello": "strings", "bass": "strings",
    "flute": "woodwinds", "piccolo": "woodwinds", "oboe": "woodwinds",
    "clarinet": "woodwinds", "bassoon": "woodwinds",
    "french_horn": "brass", "trumpet": "brass",
    "trombone": "brass", "tuba": "brass",
    "harp": "plucked", "piano": "keys",
    "choir": "vocals",
    "timpani": "percussion", "tuned_percussion": "percussion",
    "hz_taiko": "percussion", "hz_lo_taiko": "percussion", "hz_boobams": "percussion",
}

# ────────────────────────────────────────────────────────────────
# Send routing — family → bus → send level (dB)
# ────────────────────────────────────────────────────────────────
SEND_ROUTING = {
    "hall": {
        "strings":    -6.0,
        "woodwinds":  -8.0,
        "brass":     -10.0,
        "vocals":     -6.0,
        "keys":      -12.0,
        "plucked":   -10.0,
    },
    "room": {
        "strings":   -12.0,
        "woodwinds":  -8.0,
        "brass":     -10.0,
        "percussion": -6.0,
        "keys":      -10.0,
    },
    "plate": {
        "plucked":    -8.0,
        "vocals":    -10.0,
        "keys":       -8.0,
        "percussion": -10.0,
    },
}
