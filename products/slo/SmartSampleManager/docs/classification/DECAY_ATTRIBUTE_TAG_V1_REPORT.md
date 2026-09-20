# SLO Decay Attribute Tag V1 (Long/Short Decay)

**Context:** `SLO_PRODUCER_TAXONOMY_REQUIREMENTS_V1.md`'s attribute-layer section identified "Long/short decay, sustained/percussive" as the clearest genuinely-missing attribute gap once `generatePredictedTags()` was found to already exist -- unimplemented because `decayTimeSeconds` lived only in the taxonomy-only `AudioFeatures` struct, not the predicted-tags-facing `AudioAnalysisResult`. This report covers bridging that signal and the real-data calibration behind what shipped and what didn't.

## What shipped: Long Decay / Short Decay

Added `AudioAnalysisResult::decayTimeSeconds`, computed by a new shared helper `computeEnvelopeDecayTimeSeconds()` extracted from `analyzeAudioBuffer()`'s envelope-follower fix (see `DECAY_TIME_ENVELOPE_FIX_V1_REPORT.md`) so both structs' decay-time fields are computed identically rather than risking two independently-maintained measurements drifting apart. Wired into `generatePredictedTags()` following the same "absolute threshold with a documented, real-data-checked cut" pattern already used for Bright/Dark and Noisy/Tonal.

**Evidence**: re-ran the existing `ClassificationBenchmark features` mode against the real 620-file B-006 corpus (`fixtures/real_corpus_v1/audio_only`) and joined per-file `decayTimeSeconds` against the corpus manifest's `expected_subcategory` ground truth.

Per-class decay-time distribution (seconds):

| Class | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| Snare | 60 | 0.056 | 0.068 | 0.088 | 0.139 | 0.198 |
| Hi-Hat | 60 | 0.045 | 0.061 | 0.098 | 0.341 | 0.613 |
| Clap | 60 | 0.047 | 0.068 | 0.106 | 0.133 | 0.200 |
| Percussion | 60 | 0.056 | 0.078 | 0.138 | 0.247 | 0.412 |
| Kick | 60 | 0.070 | 0.107 | 0.148 | 0.219 | 0.646 |
| FX | 58 | 0.051 | 0.086 | 0.154 | 0.467 | 0.976 |
| Foley | 40 | 0.096 | 0.124 | 0.208 | 0.388 | 3.967 |
| Vocal Phrase | 41 | 0.093 | 0.166 | 0.312 | 0.720 | 2.494 |
| Impact | 31 | 0.106 | 0.179 | 0.414 | 0.985 | 2.475 |
| Bass One-Shot | 60 | 0.115 | 0.221 | 0.503 | 7.286 | 17.559 |
| Riser | 15 | 0.122 | 0.590 | 1.151 | 2.170 | 5.579 |
| Bass Loop | 15 | 0.438 | 1.300 | 1.964 | 4.934 | 7.201 |
| Atmosphere | 60 | 0.717 | 2.891 | 6.045 | 11.497 | 27.550 |

Medians order exactly as acoustic intuition predicts, with a wide overall corpus spread (p25=0.090s, p50=0.175s, p75=0.721s, p90=5.461s).

**Thresholds chosen**: `Short Decay` at `< 0.12s`, `Long Decay` at `>= 2.0s` -- deliberately leaving a wide untagged middle band (0.12s-2.0s), the same pattern as Bright/Dark and Noisy/Tonal. 0.12s sits inside the tight cluster of percussive-class medians (Snare/Hi-Hat/Clap ~0.09-0.11s) and well below Bass One-Shot's median (0.50s); 2.0s sits between Riser's median (1.15s) and Bass Loop's (1.96s), well below Atmosphere's (6.05s). Corpus-wide base rates: 34.8% of files score `< 0.12s`, 16.3% score `>= 2.0s` -- neither threshold is degenerate (near-0% or near-100%).

These are per-file absolute decay measurements, not category classifications -- a one-shot with a naturally long reverb/room tail correctly gets `Long Decay`, independent of whether it's also tagged as a one-shot elsewhere. That's the intended behavior of a decoupled attribute, not a miscalibration.

## What was investigated and rejected: Sustained / Percussive

The taxonomy doc's original phrasing paired "long/short decay" with "sustained/percussive" as if they were the same signal expressed two ways. They are not. A `decayTimeSeconds / durationSeconds` ratio (the same shape of signal already used, at a much higher and separately-calibrated threshold, by `detectLoopVsOneShot()`) was tested as a candidate for a general "Sustained"/"Percussive" attribute pair.

Per-class ratio distribution (570/620 files -- 50 files' native durations weren't readable by the quick duration-probe used for this analysis; not a correctness issue with the shipped decay-time feature itself, just a smaller evidence set for this specific rejected candidate):

| Class | n | median ratio |
|---|---|---|
| Foley | 40 | 0.058 |
| Riser | 15 | 0.066 |
| FX | 43 | 0.103 |
| Clap | 50 | 0.106 |
| Vocal Phrase | 41 | 0.118 |
| Snare | 51 | 0.150 |
| Impact | 31 | 0.185 |
| Bass Loop | 15 | 0.192 |
| Percussion | 59 | 0.195 |
| Hi-Hat | 48 | 0.220 |
| Kick | 58 | 0.233 |
| Atmosphere | 60 | 0.368 |
| Bass One-Shot | 59 | 0.400 |

This ordering is backwards from any reasonable producer intuition: **Riser has the lowest median ratio** and **Bass One-Shot the highest** -- lower than Atmosphere, higher than Bass Loop. The cause is a confound, not noise: this ratio measures how much of the *file's own length* comes after the envelope's peak. A riser's amplitude peak sits near the end of the file by design (the build climaxes right before a cut/impact), so there's almost no file left to decay across, regardless of how "sustained" the sound feels perceptually. A bass one-shot with an early transient followed by a long natural room/reverb tail can rack up a high ratio precisely because it's a one-shot, not despite it. The signal is real and correctly measured -- it just isn't measuring what a "Sustained/Percussive" tag would need it to measure.

Per this session's standing rule (a null result is a valid outcome, not a failure): **no Sustained/Percussive attribute tag ships.** `Long Decay`/`Short Decay` cover the genuinely-supported half of the original request.

## Regression verification

- New direct unit test (`test_auto_tagging_main.cpp`, `testDecayAttributeTags()`) exercises `generatePredictedTags()` against synthetic `AudioAnalysisResult` values at 2.5s (expect Long Decay), 0.05s (expect Short Decay), and 0.5s (expect neither) -- required declaring `generatePredictedTags()` in `SampleManagerEngine.h` so tests can call it directly without a full decode pipeline.
- All 28 test binaries across `ssm_qual_fast_regression`/`ssm_qual_cache`/`ssm_qual_classification`/`ssm_qual_intelligence` re-run directly (not just built) and confirmed exit-0, including `TestAudioFeatures`, `TestAutoTagging`, `TestTaxonomy`, `TestAcousticClassifierParity`.
