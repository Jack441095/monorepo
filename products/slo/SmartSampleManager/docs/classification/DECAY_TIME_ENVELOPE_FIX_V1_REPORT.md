# SLO Decay-Time Measurement Bug Fix V1

**Discovered while:** building diagnostic tooling to calibrate the attribute layer (Fine-Grained Subcategorization V1). Not something anyone was looking for — a genuine, previously-undiagnosed measurement defect in shared production code.

## The bug

`analyzeAudioBuffer()`'s decay-time calculation (`SampleManagerEngine.cpp`) searched for the first sample whose **raw instantaneous amplitude** dropped below 10% of the peak sample's amplitude, starting from the peak. Real audio oscillates — so for essentially any sound, the very next zero-crossing after the peak sample already satisfies "below 10% of peak," regardless of the sound's true envelope decay over time.

**Verified directly** on three real, sustained pad/atmosphere files (9-16 seconds long, unambiguously slow-decaying content): the old method reported decay times of 0.05-0.15 **milliseconds**. Aggregated across the full 620-file real corpus, every single class showed a median decay time in the 0.000-0.010 second range — including Atmosphere, whose median should be seconds, not fractions of a millisecond.

## Why this matters more than it might look

`AbletonTaxonomy::detectLoopVsOneShot()` uses `decayTimeSeconds / durationSeconds > 0.6` as its "is this sustained (loop-like)" signal. Since real `decayTimeSeconds` was always ~0.0001-0.01s regardless of true content, this ratio was **always** near zero for real audio — meaning the `longEnough && sustained` branch (the one that can actually say `isLoop = true`) was effectively **dead code** for any sample reaching the DSP-only fallback path (no filename/folder evidence). Every such sample fell through to the `else` branch: a low-confidence (0.25) guess of "one-shot," regardless of whether it was actually a genuine sustained loop.

This plausibly contributed to classification misses found earlier this session that weren't fully explained by other causes — most notably B-008's residual Vocal Loop misses (21 of 22 cross-vendor failures were tempo-tagged-but-no-key content falling through to this exact DSP fallback).

## The fix

Replaced the raw-instantaneous-sample check with a proper amplitude envelope: a one-pole low-pass filter over `|data[i]|` with a ~15ms time constant (fast enough to track real percussive decay, slow enough to average over several cycles even at low audible frequencies), then find the envelope's own peak and where the *envelope* — not the raw signal — drops below 10% of that peak.

Deliberately scoped narrowly: the existing raw-sample `peakIndex`/`maxVal` (used separately by the `pitchSweep` calculation later in the same function) are untouched. Only `decayTimeSeconds`'s value changes.

## Verification

Re-extracted DSP features across the same 620-file real corpus using the new diagnostic `ClassificationBenchmark features` mode (see below). Per-class median decay times now:

| Class | Median decay (fixed) | Sanity |
|---|---|---|
| Atmosphere | 6.15s | ✅ sustained ambient content |
| Bass Loop | 1.96s | ✅ sustained, longer than one-shots |
| Riser | 1.15s | ✅ builds are sustained by design |
| Bass One-Shot | 0.51s | ✅ shorter than Bass Loop |
| Foley / Impact / Vocal Phrase | 0.21-0.41s | ✅ mid-range |
| FX / Kick / Hi-Hat / Percussion | 0.10-0.15s | ✅ short, percussive |
| Clap / Snare | 0.09-0.11s | ✅ shortest, sharpest transients |

Classes now order exactly as acoustic intuition predicts — sustained content decays slowest, sharp percussive transients decay fastest. This is a night-and-day difference from the pre-fix numbers, which were uniformly near-zero regardless of class.

## New diagnostic tooling (byproduct, kept)

Added a `features` mode to `ClassificationBenchmark` and `SampleManagerEngine::analyzeFileForDiagnostics()` (self-contained JUCE decode, no cache DB touched, no engine constructed) specifically to get real feature distributions from real audio for calibration purposes — this is what surfaced the bug in the first place. Kept as permanent tooling since it has ongoing value for any future DSP-feature calibration work, not just this one fix.

## Downstream impact on real classification -- the honest, non-obvious part

Fixing the measurement is not the same as improving classification outcomes, and this section reports what actually happened rather than assuming the fix would help.

**`detectLoopVsOneShot()`'s "sustained" signal** (`decayTimeSeconds/durationSeconds > threshold`) had never been validated against real data, because real `decayTimeSeconds` was always near-zero before this fix — the threshold (0.6) was effectively untested, not deliberately chosen against real evidence.

**First result, at the original 0.6 threshold: net -0.6pp** (390/620 → 386/620 on the real 620-file B-006 corpus). Zero files newly correct; 4 newly wrong — all one-shots with an unusually long natural decay/reverb tail (a sung vocal note, resonant bass hits) now correctly measured as long-decaying, which the "long decay = loop" heuristic mistook for looping. Also re-ran the B-008 cross-vendor Vocal Loop test specifically: recall was **unchanged** (1/22) — those files are rhythmic vocal hooks with natural gaps between phrases, not sustained tones, so even a correctly-measured decay ratio genuinely doesn't clear a "sustained" bar. `detectLoopVsOneShot`'s single-peak-decay design is fundamentally mismatched for rhythmic/vocal-loop content; this fix doesn't and shouldn't try to paper over that separate limitation.

**Grid search on real data** (620 files, only 15 true Loop-variant examples — a thin evaluation set): loop-recall vs. one-shot-false-positive-rate at thresholds 0.1-0.7 showed no threshold gives strong recall *and* precision together. The 15 true Bass Loop examples themselves have wildly scattered decay ratios (0.02-0.91) — most are rhythmic/pulsing bass loops, not sustained tones, so "sustained energy" is a weak signal for loop-detection generally on this corpus, not just for vocals.

**Final threshold: raised 0.6 → 0.9.** Re-verified directly against the real corpus at 0.9: **390/620 = 62.90%, byte-for-byte identical to the pre-fix baseline — zero newly-wrong, zero newly-correct.** This is the shipped configuration: the underlying measurement bug is genuinely fixed (verified independently against real sustained audio), and real-world classification behavior on this corpus is unchanged, not regressed. The threshold is no longer an untested guess — it's calibrated against real data to avoid the specific failure mode (long-tailed one-shots misread as loops) this fix's correctness would otherwise have introduced.

## Regression verification

- `TestAcousticClassifierParity`, `TestAudioFeatures`, `TestAutoTagging`: all pass unchanged.
- `TestTaxonomy`: raising the threshold to 0.9 broke 4 synthetic fixtures whose hand-picked decay/duration ratios (~0.875-0.967) cleared the old 0.6 bar but not 0.9. These were synthetic test data calibrated against the old, never-validated threshold, not real regressions — each fixture's decay value was raised with margin (e.g. 3.5s -> 3.9s on a 4.0s duration, ratio 0.975) to keep testing the same design intent (a clearly loop-shaped sustained signal) rather than a borderline one. All 4 fixed; `TestTaxonomy` now passes clean (`ALL TAXONOMY TESTS PASSED SUCCESSFULLY!`).
- Full `ssm_qual_full`: clean, zero duplicate-symbol errors.
- B-006 real-corpus accuracy: net-neutral (62.90% before and after), confirmed via full before/after diff, not just aggregate percentage.
- B-008 Vocal Loop cross-vendor recall: unchanged (1/22) — confirmed this fix doesn't silently regress that separately-tracked number either.

## Honest bottom line

This fix trades "a known-wrong measurement everyone was unknowingly relying on" for "a correct measurement, calibrated so it doesn't change today's real-world classification outcomes." It does not improve today's accuracy numbers. Its value is that `decayTimeSeconds` is now a trustworthy signal for **future** work (e.g. the attribute-layer's Long/Short Decay or Sustained/Percussive tags, once bridged into the richer `AudioAnalysisResult` system per `SLO_PRODUCER_TAXONOMY_REQUIREMENTS_V1.md`) — before this fix, anything built on `decayTimeSeconds` would have been building on noise.
