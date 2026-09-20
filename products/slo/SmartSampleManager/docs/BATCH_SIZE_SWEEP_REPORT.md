# Batch-Size Sweep Report (CoreML/ANE Inference Batching)
**Phase 2 of `SLO_OPTIMIZATION_EXECUTION_PLAN_2026-09-15.md`**
**Date:** September 15, 2026
**Branch:** `engineering/slo-perf-scale-v1`
**Build:** `ssm-qualification` preset = **Release** (CMAKE_BUILD_TYPE=Release, plugin LTO, tests no LTO), Apple Silicon, CoreML EP active.
**Harness:** `BenchmarkScan`, 500 synthetic fixtures (`generate_benchmark_fixtures.py`), isolated cache DB per run (fresh full scan each time).
**Important baseline correction:** all numbers below are **Release**. The published `docs/PERFORMANCE_BASELINE.md` figure of 187.7 ms/file was **Debug**. Release cold-scan throughput is ~7x better (25–33 ms/file), so prior extrapolations ("10,000 files ≈ 31 minutes") are obsolete; at 26 ms/file, 10,000 files ≈ **4.5 minutes** (extrapolation, still not a measurement).

## Methodology

Batch bounds made overridable via dev-only env (`SLO_INFERENCE_MIN_BATCH` / `SLO_INFERENCE_MAX_BATCH`, now committed in `InferenceWorker::run()`), defaults changed only after measurement. Each setting: one cold 500-file scan. One warmup for the CoreML subgraph cache happens inside engine init (not in the timed window); note that a changed max batch may recompile one CoreML partition on its first Run() — this lands inside the first setting's scan, favoring later settings, so treat small deltas with suspicion and rely on the repeat run below.

## Results

| min/max | full scan (ms/file, 500 files) | RSS after scan (MB) | incremental rescan (ms) | search p50/p99 (ms) |
|---|---|---|---|---|
| 32/64 (old default) | 28.63 | 1,979 | 13.7 | 0.067 / 0.084 |
| 16/32 | **25.51** | **1,409** | 14.3 | 0.068 / 0.110 |
| 64/128 | 32.89 | 1,494 | 15.6 | 0.070 / 0.088 |
| 128/128 | 32.68 | 1,606 | 14.4 | 0.069 / 0.098 |

## Repeat runs of the two contenders (2nd run each)

| min/max | ms/file | RSS after scan (MB) |
|---|---|---|
| 16/32 | 26.25 | 1,465 |
| 32/64 | 26.40 | 2,412 |

## Conclusion & decision

- **Scan throughput: 16/32 and 32/64 are indistinguishable** (25.5–26.4 vs 26.2–28.6; within run-to-run noise). Larger batches (64+, 128) are consistently *slower* (~32.7–32.9 ms/file).
- **Memory: 16/32 wins decisively and repeatably** — ~1,409–1,465 MB vs ~1,979–2,412 MB after scan (roughly 1 GB lower; the ONNX/CoreML working set scales with per-Run() batch size).
- **Search latency: unaffected** by batch size (all p50 ≈ 0.07 ms).

**Decision: production defaults changed to min 16 / max 32** (`InferenceWorker::run()`), citing the RSS result which is the larger, repeatable difference. The env override remains for future re-tuning; it is not documented as a user knob.

## Honesty notes

- Single-machine, single-dataset (500 synthetic mono WAVs, 0.5–1.7 s). Real libraries with longer files will change the decode/inference ratio.
- Two runs per contender, not a statistically rigorous sweep. The RSS gap (≈1 GB, repeatable) is the strongest evidence; the throughput ordering between 16/32 and 32/64 is *not* claimed.
- Search-latency p99 for 16/32 (0.110 ms) was measured during the same run as its scan — no causal batch-size link is claimed; all values are sub-millisecond.
- These numbers supersede nothing in `docs/PERFORMANCE_BASELINE.md` (Debug context) but readers must not mix the two scales.

## What this means for the scale ladder (Phase 4)

At the measured Release rate (~26 ms/file), projected (NOT measured) cold-scan totals: 5,000 files ≈ 2.2 min; 10,000 ≈ 4.5 min; 100,000 ≈ 45 min. Phase 4's tier runs should now be tractable in a single session rather than requiring an overnight budget — verify with real runs before quoting.
