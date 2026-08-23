# Style Cheat Sheet (short guidance)

| Family | Tips |
|--------|------|
| EDM drops | Short phrases, heavy sidechain, kick on every downbeat, sub cuts under kick via sidechain |
| Melodic dubstep | Piano + vocal chop intro → build → half-time drop with wubs. Use setup_sidechain(kick→pad, amount=0.85) |
| Rock | Guitars panned hard L/R, kick + snare centre, bass centre, vocal centre, no sidechain |
| Pop | Vocal loudest, mild bass-kick sidechain (amount 0.5), clean HP on vocals at 100Hz |
| Classical / orchestral | Strings from bar 1, CC1 the dynamics driver, no sidechain, natural dynamics |
| Ambient | Dynamic range preserved, huge reverb sends, no limiting aggression (ambient style has bus_comp=None) |
| Jazz | Write in real time-feel (swing eighths, not quantized grid), leave space for solos, brushes not sticks, no sidechain, upright bass not synth bass |
| Cinematic / trailer | Tension via slow harmonic rhythm + rising strings, percussion hits land on structural downbeats, huge headroom for the impact moments, no pumping |
| Funk | Pocket over precision — slight behind/ahead-the-beat feel per instrument, horn stabs on the "and", bass and kick lock together (never sidechain one under the other) |
| Soul | Vocal-forward, warm low-mids (don't over-HP the vocal like pop), call-and-response backing vocals, gentle compression that rides the phrasing |

Pick a target LUFS consistent with the style — engine_master handles this.
