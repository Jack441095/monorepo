# Scale-Tier Results (5,000 / 10,000 files) — Release
**Phase 4 of `SLO_OPTIMIZATION_EXECUTION_PLAN_2026-09-15.md`**
**Date:** September 15, 2026
**Branch:** `engineering/slo-perf-scale-v1`
**Build:** `ssm-qualification` preset = **Release**, CoreML EP active, batch defaults 16/32 (see `BATCH_SIZE_SWEEP_REPORT.md`).
**Harness:** `BenchmarkScan` with the Phase 4 progress-based wait (the old fixed 10-minute cap that truncated the 5,000 tier in `docs/MEMORY_PROFILE.md` is gone). Fresh cache per run; 500/5,000/10,000 synthetic fixtures from `generate_benchmark_fixtures.py` (0.5–1.7 s mono WAVs).

## Measured results (all completed, no truncation)

| Metric | 500 (sweep baseline) | 5,000 | 10,000 |
|---|---|---|---|
| Samples processed | 500 / 500 | **5,000 / 5,000** | **10,000 / 10,000** |
| Full cold scan, total | 12.8–14.3 s | **134.1 s (2.2 min)** | **292.9 s (4.9 min)** |
| Full cold scan, per file | 25.5–28.6 ms | **26.8 ms** | **29.3 ms** |
| Incremental rescan (cache hit) | 13.7–14.4 ms total | **155 ms total** (~31 µs/file) | **290 ms total** (~29 µs/file) |
| Search p50 / p99 | 0.067 / 0.084 ms | 0.106 / 0.154 ms | 0.077 / 0.114 ms |
| RSS after scan | 1,409–1,479 MB | **1,501 MB** | **2,191 MB** |
| RSS peak | ~1,479 MB | 1,519 MB | 2,226 MB |

## Findings

1. **Per-file cost is near-linear through 10k**: 26.8 → 29.3 ms/file (+9% from 5k→10k). The historical fear that "per-file cost is very likely not linear" (`docs/PERFORMANCE_BASELINE.md`) resolves as *mildly* super-linear in this range. A 10,000-file cold scan is **minutes, not the previously projected 31 minutes** (that projection came from the Debug build).
2. **Incremental rescan scales beautifully**: ~30 µs/file flat (cache-hit path). The core "don't re-scan your library" value proposition is confirmed at 10k: full rescan of 10,000 unchanged files costs 0.29 s.
3. **Search latency stays sub-millisecond at 10k** (p99 ≈ 0.11–0.15 ms), consistent with HNSW's O(log N) behavior. No degradation concern at this scale.
4. **Memory has a real per-file marginal component**: RSS 1.50 GB @ 5k → 2.19 GB @ 10k. Decomposing against the 500-file point (~1.44 GB): fixed cost ≈ **1.4 GB** (ONNX/CoreML/JUCE working set), marginal ≈ **70–90 KB/file** (samples vector + HNSW + UMAP + cache structures). This refines `docs/MEMORY_PROFILE.md`'s "overwhelmingly fixed" conclusion: fixed dominates through ~5k, but the marginal term is real and measurable. Extrapolated (NOT measured): 100k files ≈ 1.4 GB + (9 GB) ≈ 10.4 GB — likely acceptable on 16 GB+ machines but must be *measured* before any claim.

## Honesty notes

- Synthetic fixtures (short mono WAVs) — real libraries with longer files pay more decode time; ratio shifts, per-file totals will differ.
- 5k and 10k each measured once, on a shared machine, single session. Directional conclusions (linearity, ~30 µs/file rescan) rest on two tiers agreeing with the 500-file tier; exact numbers are not claims.
- The 100k figure above is arithmetic extrapolation, explicitly **not** a measurement — the plan's no-extrapolation rule requires tier runs before quoting.
- RSS is `mach_task_basic_info` via the harness, not an Instruments trace; per-category attribution (ONNX arena vs. samples vector vs. HNSW) is still unmeasured.

## Reconciliation with `docs/PERFORMANCE_BASELINE_RELEASE.md` (Phase 2)

The Phase 2 **Release** run reported **235.9 ms/file at N=500** and **222.3 ms/file at N=1,000**,
roughly 8–9× the **25.5–28.6 ms/file** measured here at the same N=500 on the same
`ssm-qualification` preset and machine. Finding 1 above credits the older "31 minutes for 10k"
projection to the Debug build; that is only partly accurate — the 187.7 ms/file figure was Debug
(`docs/PERFORMANCE_BASELINE.md`), but the 222–236 ms/file figures were Phase 2's *Release* runs.
The gap is therefore **not** a Debug/Release artifact.

The Phase 2 harness used a fixed 10-minute wait cap (since replaced by this phase's progress-based
wait) and its N=100/N=500 runs executed under concurrent fixture-generation load — but neither
plausibly accounts for an ~8× delta. The improvement is the `engineering/slo-perf-scale-v1` work itself, not a Debug→Release effect:
`docs/BATCH_SIZE_SWEEP_REPORT.md` (Phase 2 of the optimization branch) already measured **25.5–28.6
ms/file at N=500 Release** and explicitly recorded the ~7× gain — but it framed the comparison
against `PERFORMANCE_BASELINE.md`'s 187.7 ms/file *Debug* number and did not mention that a
*Release* baseline had also measured ~222–236 ms/file. The exact code change responsible for the
gain is not itemised in either doc; it predates this phase. For the same tier, treat this
document's figures as current; both earlier per-file numbers (Debug **and** the pre-optimization
Release one) are superseded. Corollary: any doc still quoting "≈31 minutes for 10k (from the Debug
build)" is doubly wrong — the slow number was not Debug-exclusive.

## Recommended next measurement

A 100,000-file tier (~45–50 min cold scan at the measured rate) on an idle machine, with an Instruments allocation trace at 10k vs 100k to attribute the ~70–90 KB/file marginal — this is the last open question before any "handles professional libraries" claim is written.
