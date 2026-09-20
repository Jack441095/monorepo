# R&D-B — SLO V5 Intelligence Lab Report

## Baseline

V4-H remains frozen. The read-only audit found a hybrid evidence hierarchy, a frozen 16-class linear head over a 512-D PANNs CNN10 embedding, temperature-scaled confidence, and a centroid cosine OOD gate.

Measured V4 baseline from `SmartSampleManager/docs/SLO_CLASSIFICATION_V4H_FINAL_CALIBRATION_REPORT.md` and closeout material:

- Known accuracy: 76.4%
- Known macro-F1: 0.6898
- OOD AUROC: 0.911
- OOD false-known: 41.6% full / 47.2% holdout
- Selective accuracy: 73.1%
- Coverage: 88.2%
- Harmful ML overrides on known ground truth: 0

## Dataset strategy

**Status: required before model changes.** The current 1,607-file evaluation corpus is 100% one vendor/pack (KSHMR Sounds_of_KSHMR_Vol3), with 250 owner-verified OOD entries and 1,357 trusted-pack labels. It cannot establish multi-vendor generalisation.

V5 split proposal:

- TRAIN: vendor- and pack-grouped, with naming convention groups tracked.
- CALIBRATION: separate packs and naming styles; no numbered near-duplicates.
- VALIDATION: held-out packs from seen vendors.
- HELD-OUT VENDOR: entire vendor and its naming conventions withheld.
- HARD OOD: unrelated material, ambiguous labels, and adversarial filename/acoustic mismatches.

Owner-supplied licensed data should eventually cover vocals/phrases, loops/one-shots, FX/foley/risers, bass/kick/percussion boundary cases, organic material, and ambiguous/OOD samples. Do not copy or redistribute sample libraries.

## Filename intelligence result

The current tokenizer splits separators and digits, handles CamelCase, and applies ordered aliases. It has no verified vendor-specific rule layer. The filename tier can remain final even when wrong; the documented Vocal Loop defect was mostly upstream of ML. V5 should test weighted positive and negative evidence, hierarchical instrument then loop/phrase parsing, and an abstain state for ambiguity. Treat `bpm` plus key adjacency as evidence, not truth.

## OOD best candidate

**Recommendation: hybrid acoustic + filename OOD, evaluated against the frozen centroid baseline.** The baseline's centroid cosine gate is interpretable and cheap. Candidate comparison should include class-normalised distance, Mahalanobis only after covariance sufficiency is demonstrated, kNN density, ensemble disagreement, and filename/acoustic disagreement. No candidate may be called better without a multi-vendor hard-OOD set and calibrated false-known rate.

## BPM

Acoustic BPM remains experimental. The current onset/autocorrelation estimator is exact on synthetic material but reports 18.7% ±2 BPM accuracy and 42.6 BPM MAE on real loops, with systematic half-time errors. Keep BPM benchmarked separately from classification; use duration, filename evidence, candidate ranking, and confidence before any product promotion.

## Active learning

Use three states: `KNOWN`, `UNCERTAIN`, `UNKNOWN`. Prioritise uncertain samples by a mixture of calibrated entropy/margin, diversity in embedding space, and hard-negative filename/acoustic disagreement. Store only manifests and derived features unless licensed data permits otherwise.

## V5 direction

**Multi-vendor, leakage-controlled evaluation first; then filename evidence and calibrated abstention; then OOD comparison.** Do not modify the production classifier in this sprint.

## Required closeout

- **V5 DIRECTION:** held-out-vendor generalisation and calibrated abstention.
- **DATASET STRATEGY:** design ready, data acquisition required.
- **OOD BEST CANDIDATE:** hybrid acoustic + filename disagreement, not yet measured.
- **FILENAME INTELLIGENCE:** hierarchical weighted evidence with negative evidence is the highest-value research target.
- **BPM:** keep experimental; real-world accuracy currently insufficient.
- **ACTIVE LEARNING:** manifest-first uncertainty/diversity queue.
- **PRODUCTION CLASSIFIER MODIFIED:** NO.
