# Automation / Envelopes

## `envelope_add_points` / `envelope_get_points` / `envelope_clear_range`

**To remove/reset automation, use `envelope_clear_range` — it DELETES the
points.** Do NOT "clear" an envelope by writing new points (e.g. a point at
value 0) over the old ones — that doesn't remove automation, it just adds
more automation, and if you get the value wrong (see below) it silences
the track instead of resetting it to "no automation."

**Volume/Width envelope `value` is LINEAR GAIN, never dB.** `1.0` = unity
(0 dB). It is never negative — REAPER dB values (which ARE negative, e.g.
-6, -138) must be converted first: `value = 10 ** (db / 20)`.

| You want | Wrong (raw dB as value) | Right |
|---|---|---|
| 0 dB (no change) | `value: 0` (→ **silence**, not "no change") | `value: 1.0` |
| -6 dB | `value: -6` (invalid — gain can't be negative) | `value: 0.5` |
| -138 dB (~silence) | `value: -138` (invalid, not what you want anyway) | `value: 0.0` |
| +6 dB | `value: 6` | `value: 2.0` |

Pan is -1.0 (hard left) to 1.0 (hard right) — already the "natural" scale,
no conversion needed. Mute is 0.0 or 1.0. FX param envelopes are 0.0-1.0
normalized, same as `fx_set_param`.

After writing automation, verify with `envelope_get_points` before telling
the user it's done — don't assume the write matched intent.
