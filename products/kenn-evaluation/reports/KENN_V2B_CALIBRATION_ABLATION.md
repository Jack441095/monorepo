# Calibration Ablation

`KENN_GOLDEN_BENCHMARK_V2` contains 984 split-frozen synthetic cases: 360
healthy/acceptable, 385 single-fault, 143 boundary, 96 multi-fault. Splits are
development, calibration, and holdout; the manifest is machine-readable.

| Candidate | Holdout precision | Recall | Healthy FP | Abstention |
|---|---:|---:|---:|---:|
| A raw | 6.61% | 92.0% | 100% | 14.1% |
| B dual thresholds | 100% | 64.0% | 0% | 96.1% |
| C + confounders | 100% | 64.0% | 0% | 96.1% |
| D hierarchical | 100% | 62.4% | 0% | 96.2% |

The gate trades large coverage for safety. D is selected for its
detector-specific objective-fault thresholds and explicit context semantics;
it is not a production-calibrated audio detector.
