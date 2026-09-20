# SLO hard-negative pairwise correction — V1

Date: 2026-09-11

## Question

Can a narrow pairwise classifier repair the incumbent only on known class
boundaries, without replacing the calibrated nearest-centroid model?

## Protocol

- Corrected corpus: 1,553 rows, 27 eligible classes.
- Eight seeds of five-fold `StratifiedGroupKFold`, grouped by vendor/collection.
- The incumbent proposes its top two classes using standardised/L2 cosine
  nearest-centroid inference.
- A binary logistic model (`C=1.0`, class-balanced) is trained inside each
  training fold for 16 pre-registered boundaries and may arbitrate only when
  the incumbent's top two are that exact pair.
- Confidence is conservative: a corrected row's gate confidence is capped by
  both the incumbent confidence and pair-model confidence.
- No test-fold labels select pairs; no semantic labels or rename actions are
  created.

## Result

| arm | accuracy | macro-F1 | coverage @95% precision |
|---|---:|---:|---:|
| incumbent centroid | 57.99% ± 0.42 | 49.39 | 15.47% |
| pairwise correction | 58.09% ± 0.43 | 49.46 | 16.11% |
| change | **+0.11pp** | +0.07pp | +0.64pp |

The correction changed 237 predictions, but the accuracy gain is far below the
project's +2pp promotion gate. It is therefore closed as a promotion route.
The small coverage improvement is not sufficient to alter rename policy, and
the pairwise arm remains research-only.

## Receipt

`SmartSampleManager/tools/classification_benchmark/results_hard_negative_pairwise_granularity_v1.json`
