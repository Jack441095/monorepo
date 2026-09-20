# SLO class-gate validation recalibration — 120-row audit

**Date:** 2026-09-14  
**Status:** research evidence only; no production policy or rename action changed

## Purpose

The completed 120-row class-gate validation receipt was not directly consumable
by the older recalibration script. That script expected a labelled training
manifest and would previously have failed on the validation-receipt shape. The
handoff is now supported explicitly, including vendor/collection grouping.

The audit also keeps human labels outside the three candidate classes as
negative evidence. The single `Clap → Vocal One-Shot` disagreement is therefore
not silently removed from the denominator.

## Protocol

- Corpus: `candidate_embeddings_testing_v1.npz` (2048-dimensional embeddings)
- Validation receipt: `results_class_conditional_gate_validation_v1.json`
- Candidate classes: Clap, Kick, Snare
- Input rows: 120 across 15 collections
- Out-of-scope human labels retained: 1 (`Vocal One-Shot`)
- Outer split: five-fold GroupKFold by collection
- Inner calibration: three-fold StratifiedGroupKFold by collection
- Five deterministic audit seeds
- Minimum calibration predictions per class: 20
- Targets evaluated: 90% and 95%

## Results

| Target calibration precision | Held-out auto rows (5 seeds) | Descriptive held-out precision | Auto share |
| ---: | ---: | ---: | ---: |
| 90% | 586 / 600 | 99.15% | 97.67% |
| 95% | 586 / 600 | 99.15% | 97.67% |

Per-class accepted rows across the five seeds were:

| Candidate class | Auto rows | Descriptive precision |
| --- | ---: | ---: |
| Clap | 190 | 97.37% |
| Kick | 200 | 100.00% |
| Snare | 196 | 100.00% |

## Decision

This is encouraging evidence that the three-class slice is separable in this
corpus, but it is not a safe automatic tier. The sample is only 40 labelled
examples per candidate class, the held-out precision is descriptive rather
than Wilson-supported at 95%, and the validation set is limited to three
classes. The result must not be generalized to the full 28-class or open-world
classifier.

The receipt remains review-only. The next gate is a larger, independently
sealed validation set spanning the remaining candidate classes and vendors,
followed by an explicit owner decision.

Receipt: `tools/classification_benchmark/recalibrated_current_class_gates_validation_120_v1.json`

