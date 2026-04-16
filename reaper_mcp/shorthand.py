"""Compact musical notation parser for Claude mode.

Converts shorthand notation into full tracks JSON for REAPER IPC.
~8x fewer tokens than raw JSON.

Format:
  TRACK_IDX | NOTES | DYNAMICS

Notes (space-separated, sequential timing):
  D3:2.5:65     — note D3, 2.5 seconds, velocity 65
  r:2.0         — rest (silence) for 2 seconds
  @8.0          — jump clock to 8.0 seconds
  D3:4:80+F3:4:80  — chord (simultaneous notes)
  ks:0          — keyswitch: insert note at pitch 0 (C-2) for 0.1s to switch articulation

Dynamics (comma-separated, auto-generates CC1+CC11 ramps):
  pp:0-20       — pianissimo from t=0 to t=20
  mf:0-10,f:10-20,ff:20-30  — dynamic changes over time

  Dynamic markings: pp=30, p=50, mp=65, mf=80, f=100, ff=120 (CC1 values)
  CC1 (dynamics/sample layers) fades in from 0 over 0.5s at track start.
  CC11 (expression/volume) stays high (75-100).
  CC19 = reverb in Spitfire — NOT auto-generated.

  Raw CC still supported: cc1:0-16:35-112

Note names: C D E F G A B with optional # or b, then octave number.
  C4=60(middle C), D3=50, Bb2=46, F#5=78

Keyswitches (BBC Spitfire, bottom of keyboard):
  ks:0 = C-1 (articulation 1 — Long/Legato)
  ks:1 = C#-1 (articulation 2 — Spiccato/Short)
  ks:2 = D-1 (articulation 3 — Pizzicato)
  ks:3 = D#-1 (articulation 4 — Tremolo)
"""

import math

_BASE_NOTES = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}

_DYNAMICS = {'pp': 70, 'p': 80, 'mp': 90, 'mf': 100, 'f': 110, 'ff': 120}

# CC11 (expression/volume) per dynamic — stays high, never below 85
_CC11_MAP = {'pp': 85, 'p': 90, 'mp': 95, 'mf': 100, 'f': 100, 'ff': 100}

# Fade-in duration from 0 at track start — fast ramp to full
_FADE_IN_TIME = 0.25


def _note_to_midi(name: str) -> int:
    """Parse note name like D3, F#4, Bb5 to MIDI number."""
    if not name:
        raise ValueError("Empty note name")
    base = _BASE_NOTES.get(name[0].upper())
    if base is None:
        raise ValueError(f"Unknown note: {name!r}")
    i = 1

    accidental = 0
    if i < len(name) and name[i] == '#':
        accidental = 1
        i += 1
    elif i < len(name) and name[i] == 'b':
        accidental = -1
        i += 1

    octave_str = name[i:]
    try:
        octave = int(octave_str)
    except ValueError:
        raise ValueError(f"Invalid octave in note {name!r}: expected integer, got {octave_str!r}")
    midi = 12 * (octave + 1) + base + accidental
    if not 0 <= midi <= 127:
        raise ValueError(f"Note {name!r} out of MIDI range (resolved to {midi})")
    return midi


def _parse_notes(notes_str: str) -> list[dict]:
    """Parse space-separated note tokens into note dicts."""
    notes = []
    clock = 0.0

    for token in notes_str.split():
        token = token.strip()
        if not token:
            continue

        # Time jump: @8.0
        if token.startswith('@'):
            try:
                clock = float(token[1:])
            except ValueError:
                raise ValueError(f"Invalid time-jump token {token!r}: expected @<seconds>")
            continue

        # Rest: r:2.0
        if token.startswith('r:') or token.startswith('_:'):
            try:
                clock += float(token[2:])
            except ValueError:
                raise ValueError(f"Invalid rest token {token!r}: expected r:<seconds>")
            continue

        # Keyswitch: ks:0 or ks:1 etc.
        if token.startswith('ks:'):
            try:
                ks_pitch = int(token[3:])
            except ValueError:
                raise ValueError(f"Invalid keyswitch token {token!r}: expected integer pitch")
            if not 0 <= ks_pitch <= 127:
                raise ValueError(f"Keyswitch pitch {ks_pitch} out of MIDI range 0-127 (token {token!r})")
            notes.append({
                "pitch": ks_pitch,
                "velocity": 100,
                "start": round(clock, 4),
                "end": round(clock + 0.1, 4),
            })
            # Don't advance clock — keyswitch is instantaneous
            continue

        # Chord: D3:4:80+F3:4:80
        chord_parts = token.split('+')
        max_dur = 0.0

        for part in chord_parts:
            segs = part.split(':')
            if len(segs) < 3:
                raise ValueError(
                    f"Malformed note token {part!r}: expected Note:Duration:Velocity "
                    f"(e.g. D3:2.5:65)"
                )
            name = segs[0]
            try:
                dur = float(segs[1])
            except ValueError:
                raise ValueError(f"Invalid duration in {part!r}: expected number, got {segs[1]!r}")
            try:
                vel = int(segs[2])
            except ValueError:
                raise ValueError(f"Invalid velocity in {part!r}: expected int, got {segs[2]!r}")
            if not 1 <= vel <= 127:
                raise ValueError(f"Velocity {vel} out of range 1-127 in {part!r}")
            if dur <= 0:
                raise ValueError(f"Duration {dur} must be > 0 in {part!r}")
            pitch = _note_to_midi(name)

            notes.append({
                "pitch": pitch,
                "velocity": vel,
                "start": round(clock, 4),
                "end": round(clock + dur, 4),
            })
            max_dur = max(max_dur, dur)

        clock += max_dur

    return notes


def _cc_ramp(cc_num: int, t_start: float, t_end: float, v_start: int, v_end: int) -> list[dict]:
    """Generate interpolated CC ramp every 0.5s."""
    ccs = []
    duration = t_end - t_start
    if duration <= 0:
        ccs.append({"cc_number": cc_num, "cc_value": max(0, min(127, v_start)),
                     "position": round(t_start, 3), "channel": 0})
        return ccs

    step = 0.5
    num_points = max(2, int(duration / step) + 1)
    for i in range(num_points):
        frac = i / (num_points - 1)
        t = t_start + duration * frac
        v = v_start + (v_end - v_start) * frac
        ccs.append({"cc_number": cc_num, "cc_value": max(0, min(127, int(round(v)))),
                     "position": round(t, 3), "channel": 0})
    return ccs


def _parse_ccs(cc_str: str, t_min: float, t_max: float) -> list[dict]:
    """Parse dynamics/CC string into CC events.

    Supports:
      Dynamic markings: pp:0-20,f:20-40  (auto CC1+CC11 ramps)
      Raw CC: cc1:0-16:35-112
      Mixed: pp:0-20,cc1:20-30:80-120

    Features:
      - CC1 (dynamics) fades in from 0 over 0.5s at track start
      - CC11 (expression) stays high (75-100), mapped per dynamic level
      - CC19 is reverb in Spitfire — NOT auto-generated
    """
    ccs = []
    has_cc11 = False
    has_dynamics = False

    if not cc_str.strip():
        # No CC specified — fast ramp to 100, hold there
        if t_max > t_min:
            ccs.extend(_cc_ramp(1, t_min, t_min + _FADE_IN_TIME, 0, 100))
            ccs.extend(_cc_ramp(1, t_min + _FADE_IN_TIME, t_max, 100, 100))
            ccs.extend(_cc_ramp(11, t_min, t_max, 100, 100))
        return ccs

    # Collect dynamic segments to chain them as CC1+CC11 ramps
    dyn_segments = []  # (t_start, t_end, dyn_name)

    for ramp in cc_str.split(','):
        ramp = ramp.strip()
        if not ramp:
            continue

        parts = ramp.split(':')
        tag = parts[0].strip().lower()

        # Dynamic marking: pp:0-20 or ff:10-30
        if tag in _DYNAMICS:
            has_dynamics = True
            has_cc11 = True  # dynamics auto-generate CC11
            time_parts = parts[1].split('-')
            t_start = float(time_parts[0])
            t_end = float(time_parts[1])
            dyn_segments.append((t_start, t_end, tag))
            continue

        # Raw CC: cc1:0-16:35-112
        if tag.startswith('cc'):
            try:
                cc_num = int(tag.replace('cc', ''))
            except ValueError:
                raise ValueError(f"Invalid CC tag {tag!r}: expected ccN (e.g. cc1, cc11)")
            if not 0 <= cc_num <= 127:
                raise ValueError(f"CC number {cc_num} out of range 0-127 in {ramp!r}")
            if cc_num == 11:
                has_cc11 = True
            if len(parts) < 3:
                raise ValueError(f"Malformed CC ramp {ramp!r}: expected ccN:start-end:v1-v2")
            time_parts = parts[1].split('-')
            val_parts = parts[2].split('-')
            if len(time_parts) < 2 or len(val_parts) < 2:
                raise ValueError(f"Malformed CC ramp {ramp!r}: expected ccN:start-end:v1-v2")
            t_start = float(time_parts[0])
            t_end = float(time_parts[1])
            v_start = int(val_parts[0])
            v_end = int(val_parts[1])
            ccs.extend(_cc_ramp(cc_num, t_start, t_end, v_start, v_end))
            continue

        raise ValueError(
            f"Unknown CC tag {tag!r} in {ramp!r}: expected dynamic (pp/p/mp/mf/f/ff) or ccN:start-end:v1-v2"
        )

    # Convert dynamic segments to CC1 + CC11 + CC19 ramps
    if dyn_segments:
        dyn_segments.sort(key=lambda x: x[0])

        # Fade-in: CC1 and CC19 start from 0 over 0.5s before first dynamic target
        first_t_start = dyn_segments[0][0]
        first_cc1 = _DYNAMICS[dyn_segments[0][2]]
        first_cc11 = _CC11_MAP[dyn_segments[0][2]]

        # Insert fade-in from 0 at track start
        fade_end = first_t_start + _FADE_IN_TIME
        ccs.extend(_cc_ramp(1, first_t_start, fade_end, 0, first_cc1))
        ccs.extend(_cc_ramp(11, first_t_start, fade_end, 0, first_cc11))

        for i, (t_start, t_end, dyn_name) in enumerate(dyn_segments):
            cc1_target = _DYNAMICS[dyn_name]
            cc11_target = _CC11_MAP[dyn_name]

            if i == 0:
                # First segment: start after fade-in
                seg_start = t_start + _FADE_IN_TIME
                prev_cc1 = first_cc1
                prev_cc11 = first_cc11
            else:
                seg_start = t_start
                prev_cc1 = _DYNAMICS[dyn_segments[i - 1][2]]
                prev_cc11 = _CC11_MAP[dyn_segments[i - 1][2]]

            if seg_start < t_end:
                ccs.extend(_cc_ramp(1, seg_start, t_end, prev_cc1, cc1_target))
                ccs.extend(_cc_ramp(11, seg_start, t_end, prev_cc11, cc11_target))

    # Auto-add flat CC11=100 if not explicitly provided
    if not has_cc11 and t_max > t_min:
        ccs.extend(_cc_ramp(11, t_min, t_max, 100, 100))

    return ccs


def parse_shorthand(text: str) -> list[dict]:
    """Parse compact notation into a list of track dicts for REAPER IPC.

    Each line: TRACK_INDEX | NOTES | DYNAMICS
    Lines starting with # are comments.
    Multiple lines with the same track_index are merged automatically.

    Returns list of {track_index, notes, ccs} dicts.
    """
    track_map: dict[int, dict] = {}  # track_index -> {notes, ccs}

    for line_num, line in enumerate(text.strip().split('\n'), start=1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        parts = line.split('|')
        if len(parts) < 2:
            raise ValueError(
                f"Line {line_num}: malformed shorthand {line!r} — "
                f"expected 'TRACK|NOTES' or 'TRACK|NOTES|CCs'"
            )

        try:
            track_index = int(parts[0].strip())
        except ValueError:
            raise ValueError(f"Line {line_num}: track index must be int, got {parts[0]!r}")
        if track_index < 0:
            raise ValueError(f"Line {line_num}: track index must be >= 0, got {track_index}")

        try:
            notes = _parse_notes(parts[1].strip())
        except ValueError as e:
            raise ValueError(f"Line {line_num}: {e}") from e

        # Find time range from notes for auto CC
        t_min = min((n["start"] for n in notes), default=0.0)
        t_max = max((n["end"] for n in notes), default=0.0)

        try:
            ccs = _parse_ccs(parts[2].strip() if len(parts) > 2 else "", t_min, t_max)
        except (ValueError, KeyError) as e:
            raise ValueError(f"Line {line_num}: CC parse error: {e}") from e

        if track_index in track_map:
            track_map[track_index]["notes"].extend(notes)
            track_map[track_index]["ccs"].extend(ccs)
        elif notes:
            track_map[track_index] = {
                "track_index": track_index,
                "notes": notes,
                "ccs": ccs,
            }

    return list(track_map.values())


def is_shorthand(text: str) -> bool:
    """Check if a string looks like shorthand notation (vs JSON)."""
    text = text.strip()
    if text and text[0] in '0123456789#':
        return '|' in text
    return False
