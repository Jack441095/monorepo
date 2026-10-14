# E2 grade out of 100: what exists and a proposal to decide on

14 October 2026. Written so the weights can be decided in one sitting. Nothing here is implemented.

## What exists

`core/mix_doctor.py` already produces a 0-100 score (`mqm_score`) and a letter grade (S at 90, A at 80, B at 70, C at 60, D at 50, then CRITICAL). It is five dimensions of 20 points each: dynamic health, low-end control, spectral balance, stem separation, stereo imaging. Each one starts at 20 and loses fixed amounts when a rule trips (for example true peak above -0.2 dBTP costs 10 points, master correlation below 0 costs 15).

Three problems for E2:

1. **Missing measurements become healthy numbers.** `_extract_telemetry` falls back to -14 LUFS, -1 dBTP, correlation 0.88, crest 10 dB and 0.25 in every band when a meter is absent. A mix with no stereo reading therefore scores as if its correlation were good. E2 must never invent a number, so a missing measurement has to stay missing.
2. **The deductions have no stated source.** The 10, 6, 5, 3 point steps and the thresholds are not tied to a standard, a reference or a measurement. A second analyst could not reproduce the grade from written rules.
3. **It grades against nothing the producer chose.** There is no reference track or declared target. `packages/mix-review/core/reference_matching.py` can already compare a mix to a reference (7-band spectrum, dynamics, stereo) and is the natural source for that part.

## Proposal

Three parts, each scored only from what was actually measured.

| Part | Points | Scored from |
|---|---|---|
| Technical health | 30 | clipping and true peak against a ceiling, stereo correlation and mono cancellation, DC offset. Hard failures, the same for every mix |
| Declared target | 30 | the producer's stated goal: loudness (integrated LUFS) within a tolerance, true-peak ceiling, genre or delivery target. Only scored if they declared one |
| Reference match | 40 | the producer's own reference track: spectrum balance, dynamics (crest, loudness range), stereo width, compared by `reference_matching` |

Rules that make it reproducible and honest:

- **A part with no evidence is not scored, and the grade says so.** With no reference the grade is out of 60 and shown as "42 of 60, no reference supplied". It is not rescaled to look like a full 100.
- **Every deduction names its source**: a published convention (a streaming loudness target, a true-peak ceiling), the producer's reference, or the producer's declared target. Nothing without a source loses points.
- **Same inputs, same grade**, with the rule table written down so a second analyst gets the same answer.
- **The grade is advisory.** It never applies a change by itself.

## Decisions needed

1. **Weights.** Is 30 / 30 / 40 right, or should the reference match count for more or less?
2. **No reference.** Show a partial grade (out of 60), or decline to grade until a reference or target is given?
3. **Which conventions count** for the declared-target part: a fixed list of streaming targets, or only what the producer states?
4. **What happens to the current five-dimension score.** Keep it as the technical-health part, rework it, or retire it?
5. **Letter grades.** Keep S/A/B/C/D, or show only the number?
