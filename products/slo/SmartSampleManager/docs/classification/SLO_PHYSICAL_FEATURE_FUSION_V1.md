# SLO physical-feature fusion experiment — V1

Date: 2026-09-11

## Question

Do explicit waveform measurements add enough information to improve the
corrected Perch+CLAP classifier, rather than serving only as explanations?

## Protocol

- Corpus: `corpus_granularity_relabelled_v1.npz`, 1,553 rows and 27 eligible
  classes.
- Features: 22 read-only definition-card measurements covering duration,
  loudness, crest/clipping, silence, spectrum, onset/periodicity, pitch, and
  stereo correlation.
- Evaluation: eight seeds of five-fold `StratifiedGroupKFold`, grouped by
  vendor/collection; scaling and missing-value imputation were fit inside each
  training fold.
- Classifier: standardise each feature block, L2-normalise rows, concatenate
  the acoustic block at the stated weight, then use the same nearest-centroid
  classifier as the incumbent.
- Safety: source audio was read-only; no semantic labels, production model, or
  rename action was created or changed.

## Result

| acoustic block weight | accuracy | macro-F1 | coverage @95% precision | delta vs embedding-only |
|---:|---:|---:|---:|---:|
| 0 (embedding only) | 57.99% | 49.39 | 15.47% | 0.00pp |
| 0.25 | 57.99% | 49.39 | 15.52% | +0.01pp |
| 0.50 | 57.99% | 49.38 | 15.59% | 0.00pp |
| 1.00 | 58.02% | 49.48 | 15.83% | **+0.03pp** |

The largest change is far below the project’s +2pp promotion gate. Physical
features therefore remain an evidence and explanation layer, not a promoted
classification arm. The 1,553 definition cards are retained for future review,
calibration, and human-audit tooling.

## Receipts

- Evaluation: `SmartSampleManager/tools/classification_benchmark/results_physical_feature_fusion_granularity_v1.json`
- Cards: `SmartSampleManager/tools/classification_benchmark/results_physical_feature_cards_granularity_v1.json`
- Reproducible runner: `SmartSampleManager/tools/classification_benchmark/evaluate_physical_feature_fusion.py`
