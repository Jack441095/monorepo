# KENN V2-B Baseline Reproduction

The unmodified V2-A harness was rerun before V2-B calibration work. It uses
the same seeded 240-case manifest and full-report Mix Review path. The saved
stdout is `results/v2b_baseline_reproduction_stdout.json`; the result artifact
is the frozen historical `KENN_GOLDEN_BENCHMARK_V1_results.json`.

Expected headline values are retained: 240 total cases, 50 healthy controls,
100% healthy false-positive rate, 83.33% multi-fault recall, 0% headroom and
L/R imbalance recall, and 33.33% clipping recall. No V2-A definition changed.
