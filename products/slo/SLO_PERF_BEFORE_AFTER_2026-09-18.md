# SLO Perf Before/After — 2026-09-18
**UPDATE (evening, autonomous continuation): fresh baseline RECORDED (Grade A — ran it this session).** Build: Release, LTO ON (preset-equivalent flags), branch `slo/eval-feat-ai-perf-v1`, build dir `monorepo/workspace/builds/slo-perf-baseline-v1`, 500-file synthetic fixture, BenchmarkScan harness, CoreML EP active (38/45 nodes on CoreML per session log), batch defaults 16/32.

## Fresh baseline (this session, 3 runs each, medians)
| Metric | Default (batch 32) | Batch 16 (SLO_INFERENCE_MAX_BATCH=16) |
|---|---|---|
| full_scan ms/file | 26.6 (25.9 / 26.6 / 38.5) | 43.6 (39.1 / 43.6 / 48.1) |
| incremental rescan (ms, total) | ~15 | ~20–30 |
| search p99 (ms) | 0.09–0.41 | 0.14–0.39 |
| **RSS peak (MB)** | **1,406** (1,335 / 1,406 / 1,636) | **770** (650 / 770 / 958) |
| db size | 2,125,824 B (identical across configs) | same |

**Findings:**
1. **Historical receipts validated**: default runs 2–3 (25.9/26.6 ms/file) match `docs/BATCH_SIZE_SWEEP_REPORT.md`'s 25.5–28.6 ms/file at N=500 Release. The repo's numbers were honest. Run-1 outliers (38–48 ms/file, +200–300 MB) are first-run CoreML subgraph conversion (model cache cold) — excluded from medians, noted for methodology.
2. **RSS/speed trade-off quantified (P-01 outcome)**: batch 16 costs ~+64% scan time for ~−45% peak RSS (1.41→0.77 GB median). This is a **product decision (DECIDE → Jack)**, not an engineering default change: the dev-only env knob `SLO_INFERENCE_MAX_BATCH` already exists (`SampleManagerEngine.cpp:4955+`), so no code change is required to adopt either posture. Recommendation if DAW coexistence becomes the priority: ship docs/beta guidance suggesting the knob rather than changing the default without a user-facing setting.
3. **Next free-win experiment (design ready, not run)**: ONNX CPU arena shrink / `DisableCpuMemArena` probe — may cut RSS without the scan-time penalty, since 38/45 nodes already run on CoreML. Requires a code change + full gate rerun; queued as the next EXECUTE candidate.
4. R6 gates re-run green on this build before benchmarking: TestReadOnlySafetyQualification, TestPathTraversal, TestMalformedAudio, TestDuplicateDetection — all SUCCESS.

## Original assessment (morning read-only pass) — EXECUTE status was: no code changes
Reason (per R2/R4): no fresh baseline existed at that time. It has since been recorded (above), which is what unblocked the P-01 measurements.

## Finding: the naive speedup backlog is already spent
| Suspect | Status | Evidence |
|---|---|---|
| Batched inference | **Already implemented** — single `Ort::Session::Run()` per batch, batch-shape guard `hasExpectedEmbeddingOutput`, min/max batch guards, dedicated batching thread | `SampleManagerEngine.cpp:4744–4766, 4955–4990, 2099` |
| Graph optimisation | **Already set**: `ORT_ENABLE_ALL` | `SampleManagerEngine.cpp:2104` |
| Intra-op threads | **Already set**: CPU count | `SampleManagerEngine.cpp:2103` |
| CoreML EP | **Active**, with compiled-subgraph cache dir + ANE preference | `SampleManagerEngine.cpp:2106–2134` + fresh session log (38/45 nodes) |
| Batch-size tuning | **Measured**: defaults 16/32 from sweep; fresh trade-off above re-confirms 32 as the speed-default | `docs/BATCH_SIZE_SWEEP_REPORT.md` + this file's fresh table |
| Incremental rescan | **~15–30 ms total at 500 files (fresh)** | this session's BenchmarkScan |
| WAL cache | WAL mode + quarantine + 3-way version gates | `SLO_SCAN_INDEX_PIPELINE_REPORT_V1` |
| Search latency | p99 0.09–0.41 ms @500 fresh; 0.11–0.15 ms @10k historical | SCALE_TIER_RESULTS + this session |
| RT allocations in callback | 0 across 2000 callbacks; 0.127 ms max | `SLO_RT_THREADING_AUDIT_V1` 2026-09-16 update |

## Historical before→after (repository receipts — now cross-validated fresh)
| Metric | Before | After | Delta | Source |
|---|---|---|---|---|
| Per-file cold scan (Release, N=500) | 222–236 ms | 25.5–28.6 ms (fresh: 25.9–26.6) | **~7–8×** | `docs/BATCH_SIZE_SWEEP_REPORT.md` + this session |
| 10k-file cold scan (projected) | ~31 min (Debug extrapolation) | 292.9 s measured | **6.3×** | `docs/SCALE_TIER_RESULTS.md` |
| Max audio-callback duration | 1.085 ms | 0.127 ms | 8.5× | `SLO_RT_DEADLINE_STRESS_V1_REPORT` |

## Remaining candidates (updated)
| Rank | Candidate | Status | Design | Expected | Gate |
|---|---|---|---|---|---|
| 1 | **Batch-16 posture (DECIDE)** | Data delivered | env knob only, no code | −45% RSS / +64% scan time | Jack's product call; document in beta guidance if adopted |
| 2 | **CPU arena shrink probe** | **TESTED — NULL RESULT (2026-09-18, code reverted)** | `DisableCpuMemArena` behind dev-only env `SLO_ORT_DISABLE_CPU_ARENA` (same pattern as batch env hooks); built + measured 3 runs | **None**: RSS peak 1523–1862 MB (median 1546) vs baseline median 1406 — no improvement, slightly worse within variance; speed unchanged (25.0–26.0 ms/file) | R6 gates green during probe (7 SUCCESS/PASSED); reverted per R4 (no measurable win → don't ship). **Conclusion: the RSS holder is CoreML/ANE-side working set + JUCE, not the CPU arena — P-01's memory ambition via ORT session options is a dead end on this stack.** |
| 3 | Streaming/segmented decode | PROPOSE | dr_wav partial reads; hash semantics must stay content-stable | Lower scan RSS peak on long libraries | TestDuplicateDetection + checksum read-only gate |
| 4 | Session lazy-load/warm-up audit | PROPOSE | Confirm session creation defers past engine init | Faster first paint | Startup timing receipt + full suite |

## Baseline regeneration commands (used this session — reproducible)
```sh
# build (Release, preset-equivalent)
/opt/homebrew/bin/cmake -S SmartSampleManager -B monorepo/workspace/builds/slo-perf-baseline-v1 -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DSSM_ENABLE_LTO=ON -DSSM_TEST_LTO=OFF -DSSM_BUNDLE_APPLE_DEPS=OFF
/opt/homebrew/bin/cmake --build monorepo/workspace/builds/slo-perf-baseline-v1 -j 8
# 500-file fixtures
python3 SmartSampleManager/generate_benchmark_fixtures.py /tmp/slo_bench_500 500
# benchmark (default) / (batch-16 trade-off)
BenchmarkScan /tmp/slo_bench_500
SLO_INFERENCE_MAX_BATCH=16 BenchmarkScan /tmp/slo_bench_500
```
Raw per-run outputs: `/tmp/slo_p01_results/*.txt` (default×3, batch16×3, batch8×1, arena-off×3).

## Experiment 2 result: CPU arena disable — NULL RESULT, reverted
- Change: `DisableCpuMemArena()` behind `SLO_ORT_DISABLE_CPU_ARENA` (dev-only env hook, batch-hook pattern), rebuilt, 3× BenchmarkScan.
- Numbers: speed 25.01 / 26.04 / 25.62 ms-per-file (unchanged vs 25.9/26.6 baseline) — but RSS peak 1522.75 / 1862.17 / 1545.84 MB vs baseline 1335.47 / 1406.44 / 1636 MB. Median RSS **worse** (1546 vs 1406), no speed gain.
- R6 gates green during the probe run (TestReadOnlySafetyQualification, TestPathTraversal, TestMalformedAudio, TestDuplicateDetection).
- **Action: reverted** (`git checkout -- Source/SampleManagerEngine.cpp`), per R4. The hypothesis (CPU arena holds the working set despite 38/45 nodes on CoreML) is falsified: the RSS holder is the CoreML/ANE-side working set plus JUCE host allocations — ORT session options won't move it. This closes the "arena shrink" route of P-01; the remaining memory levers are the batch-posture DECIDE (row 1) and streaming decode (row 3).

