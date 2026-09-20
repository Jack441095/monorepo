# SLO acoustic tempo estimator — V5 experimental report

**Date:** 2026-09-14  
**Status:** experimental evidence; not an auto-rename qualification

## What changed

The estimator now combines broadband, low-frequency and air-band onset cues.
Long files receive a separate tempo view capped at 20 seconds, and the
production path accepts an acoustic BPM only when the 5-second and long views
agree within 2 BPM. Filename parsing also recognizes the explicit
loop-plus-key convention (`Loop_110_Fm`, `Loop_01_160_C#`).

## Reproducible evaluation

The native command is:

```bash
ClassificationBenchmark tempo <corpus> <receipt.json>
```

The evaluator excludes one-shots from accuracy aggregates. A reference must
have a plausible BPM token, an explicit loop signal in its path/name, and at
least two seconds of audio. It still writes every decoded row to the receipt,
including ineligible rows, so the denominator is inspectable.

Receipt: `_artifacts/slo_tempo_real_fixture_eval_v4.json`

Results over `real_corpus_v2/full_evidence`:

| Measure | Result |
|---|---:|
| Files decoded | 5,157 |
| Eligible loop references | 104 |
| Fused estimates accepted | 52 |
| Fused estimates abstained | 52 |
| MAE on accepted estimates | 24.42 BPM |
| Exact within ±0.5 BPM | 12 / 104 |
| Within ±1 BPM | 16 / 104 |
| Within ±2 BPM | 16 / 104 |

The low-band prior improves the matched short-view comparison on the same
eligible files from 30.46 to 28.57 BPM MAE (76 versus 75 non-unknown rows).
The fused value is safer and lower-error on accepted rows, but coverage falls;
this is a selective-risk trade-off, not proof of general tempo correctness.

## Interpretation and next gate

The result confirms that multi-band and multi-view evidence reduce some
subdivision errors, while also confirming that filename BPM is only a weak
reference and that notated-versus-felt tempo is genuinely ambiguous. Acoustic
BPM remains review-only. A promotion decision needs independently verified,
collection-held-out BPM labels and a comparison against a dedicated beat/tempo
model before exposing an automatic naming tier.

## Dedicated beat-tracker comparison (research-only)

The comparison runner
`SmartSampleManager/tools/classification_benchmark/evaluate_tempo_backends.py`
was run against the same 104 eligible loop references using
`librosa.beat.beat_track` on up to 20 seconds of mono audio. The immutable
receipt is
`products/slo/_artifacts/slo_tempo_backend_comparison_v1_20260914.json`.

The beat tracker accepted 102/104 rows at 30.27 BPM MAE (14.59 BPM when
half/double-time equivalents are allowed). The incumbent fused estimator
accepted 52/104 at 24.42 BPM MAE (14.60 BPM octave-aware). This comparison does
not justify swapping in a generic beat tracker: it raises coverage but worsens
absolute error and does not improve octave-aware error. Better tempo quality
therefore requires stronger, independently verified beat labels and/or a
specialized temporal model, not another uncalibrated backend.

## Padded-window correction (2026-09-14)

The production path still uses a fixed 5-second waveform for PANNs inference,
but the short tempo view now receives only the samples represented by the true
decoded duration. This prevents trailing model-padding silence on 2–5-second
loops from contributing empty beat intervals. The true-duration `<2 s` gate
remains in force, and long files continue to use the separate up-to-20-second
view. This is a scope/correctness fix; it does not change the benchmark's weak
filename-derived reference labels or turn acoustic BPM into an auto-rename
decision.

The taxonomy boundary was also tightened: an ML-OOD semantic abstention no
longer clears a measured BPM when the filename still carries explicit loop
structure. Independent physical evidence stays visible while the semantic
class remains review/unknown.
