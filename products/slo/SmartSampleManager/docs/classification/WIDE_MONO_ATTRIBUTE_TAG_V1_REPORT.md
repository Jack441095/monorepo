# SLO Wide/Mono Attribute Tag V1

**Context:** `SLO_PRODUCER_TAXONOMY_REQUIREMENTS_V1.md`'s attribute-layer section listed "Wide/mono" as genuinely missing -- neither `AudioFeatures` nor `AudioAnalysisResult` looked at channel phase/count at all before this pass.

## Evidence-gathering false start (worth recording)

A first attempt used Python's stdlib `wave` module to compute inter-channel Pearson correlation directly against the real 620-file B-006 corpus's stereo files. It only successfully parsed 75 of 447 stereo files -- the module can't handle some of the real formats present (likely 24-bit PCM, float32, and/or `WAVE_FORMAT_EXTENSIBLE` headers), and several per-class buckets fell to n<=4. That's too thin to calibrate a threshold honestly, so no threshold was chosen from it.

Instead, a `stereo` mode was added to `ClassificationBenchmark` (`classification_benchmark_main.cpp`) using JUCE's `AudioFormatReader` -- the same robust decode path used everywhere else in this codebase (e.g. `analyzeFileForDiagnostics()`) -- which processed all 620 files without error, 495 of them genuinely stereo (125 mono).

## Real-corpus evidence

Per-class distribution of L/R Pearson correlation, stereo files only (495/620):

| Class | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| Riser | 15 | 0.085 | 0.098 | 0.177 | 0.269 | 0.569 |
| Atmosphere | 45 | -0.022 | -0.001 | 0.511 | 1.000 | 1.000 |
| Foley | 25 | 0.060 | 0.287 | 0.586 | 0.660 | 0.754 |
| Clap | 60 | -0.223 | 0.023 | 0.696 | 0.960 | 1.000 |
| Impact | 31 | 0.119 | 0.409 | 0.859 | 0.918 | 0.962 |
| Hi-Hat | 56 | 0.028 | 0.313 | 0.870 | 1.000 | 1.000 |
| FX | 44 | 0.005 | 0.313 | 0.877 | 1.000 | 1.000 |
| Percussion | 38 | 0.380 | 0.796 | 0.952 | 1.000 | 1.000 |
| Snare | 53 | 0.687 | 0.846 | 0.959 | 0.999 | 1.000 |
| Bass Loop | 15 | 0.804 | 0.921 | 0.973 | 0.998 | 0.999 |
| Kick | 55 | 0.892 | 0.965 | 0.997 | 1.000 | 1.000 |
| Bass One-Shot | 32 | 0.677 | 0.964 | 0.998 | 0.999 | 1.000 |
| Vocal Phrase | 26 | -0.202 | 0.070 | 1.000 | 1.000 | 1.000 |

Unlike the rejected Sustained/Percussive ratio (see `DECAY_ATTRIBUTE_TAG_V1_REPORT.md`), this ordering is coherent and matches well-known mixing convention rather than contradicting it: Bass (Loop and One-Shot), Kick, Snare, and Percussion -- content mix engineers routinely keep mono/centered for mono-compatibility and low-end translation -- cluster at correlation 0.95-1.00. Riser, Atmosphere, and Foley -- content routinely processed with stereo widening, chorus, or wide reverb -- sit at the low end (median 0.18-0.59). Vocal Phrase's median of exactly 1.000 also matches convention (vocal one-shots are very often rendered/exported as dual-mono), while its low p10/p25 shows a real minority of genuinely wide, double-tracked, or heavily-reverbed vocal content -- both behaviors are individually plausible and expected, not evidence of a broken measurement.

Corpus-wide (495 stereo files): p25=0.438, median=0.905, p75=0.999. Candidate base rates: `< 0.5` (Wide) = 26.5% of stereo files; `>= 0.98` (Mono-compatible) = 38.0%. Neither is degenerate.

## What shipped

Added `AudioAnalysisResult::stereoCorrelation` (default 1.0, matching a genuinely mono source), computed in `analyzeAudioProperties()` from the pre-downmix interleaved buffer using channels 0/1 as L/R (Pearson correlation over the full file; silence/DC in a channel is treated as mono-compatible rather than undefined).

Tag logic in `generatePredictedTags()`:
- `originalChannels == 1` -> **Mono** (no threshold needed -- a genuinely mono file is unambiguously mono).
- `originalChannels >= 2` and `stereoCorrelation >= 0.98` -> **Mono** (mono-compatible in practice, whether truly mono-summed or literal mono content stored in a stereo container).
- `originalChannels >= 2` and `stereoCorrelation < 0.5` -> **Wide**.
- Otherwise (0.5-0.98 correlation): untagged, same wide-middle-band pattern as Bright/Dark, Noisy/Tonal, and Long/Short Decay.

## Regression verification

- New direct unit test (`test_auto_tagging_main.cpp`, `testWideMonoAttributeTags()`) exercises `generatePredictedTags()` against a mono file (expect Mono), stereo correlation=0.995 (expect Mono), stereo correlation=0.2 (expect Wide), and stereo correlation=0.7 (expect neither).
- All affected test binaries (`TestAutoTagging`, `TestAudioFeatures`, `TestTaxonomy`, `TestAcousticClassifierParity`) run directly and confirmed exit-0.
