# KENN_GOLDEN_BENCHMARK_V1 Report

The executable benchmark is `benchmark/run_golden_benchmark.py`; the frozen
machine-readable result is `results/KENN_GOLDEN_BENCHMARK_V1_results.json`.
It uses seeded in-memory 48 kHz 16-bit PCM and programmatic injection.

Coverage: clipping, headroom, DC, bass/HF excess, resonance, mud, harshness,
L/R imbalance, anti-phase, wide bass, compression, transients, silence,
near-silence, noise, five-severity sweeps, 30 compound cases, and 50 controls.

Important result: all 50 controls emitted flags. Therefore precision, overall
F1, harmful-advice rate, and severity calibration must be recorded as **not
qualified**, rather than presented as an optimistic aggregate. The benchmark
does not make aesthetic tone or genre a defect label.
