# SmartSampleManager — Memory Profile (Phase 2)

Answers Phase 1's open question ("is the ~3.9 MB/file RSS growth fixed overhead or genuine per-file retention?") with a real RSS-vs-N curve. Harness: same `BenchmarkScan` used for `docs/PERFORMANCE_BASELINE.md`, this time built **Release** (`build-release/`, `-DCMAKE_BUILD_TYPE=Release`), same machine (Apple Silicon Mac, CoreML execution provider active), same synthetic fixtures (`generate_benchmark_fixtures.py`). RSS read via `mach_task_basic_info` (`residentMemoryBytes()` in `Source/benchmark_scan_main.cpp`), not a separate profiler — Instruments was not used in this pass (see "What wasn't done" below).

## What was actually run

Fresh cache per run (`clearCache()` before each), so every number below is a real cold decode+embed+index cost, not a cache hit.

| N (files) | RSS before init | RSS after full scan | RSS "peak" (post-search) | Notes |
|---|---|---|---|---|
| 0 | 16.5 MB | 187.5 MB | 187.5 MB | Pure init cost: JUCE + ONNX Runtime + CoreML EP, zero files |
| 100 | 16.5 MB | 1,664.0 MB | 1,664.0 MB | Ran concurrently with background fixture generation for later tiers — see caveat below (timing only, not RSS) |
| 500 | 16.4 MB | 2,286.4 MB | 2,288.8 MB | Same concurrent-generation caveat |
| 1,000 | 16.4 MB | 1,907.1 MB | 1,806.9 MB | Clean run, no concurrent load |
| 5,000 (requested) | 16.4 MB | 2,911.3 MB | 2,576.1 MB | **Incomplete** — see below |

The `BenchmarkScan` "peak" field is not a running maximum; it's a second RSS read taken after the search-latency loop. It can be *lower* than "after scan" (see N=1,000: 1,806.9 < 1,907.1) — a sign that some memory genuinely gets freed after the scan phase, not that the peak-tracking is broken.

### 5,000-file tier — incomplete, flagged rather than reported as clean

The harness has a hardcoded 10-minute wait cap (`waitLimit = 6000` at 100 ms polls) in both the full-scan and incremental-rescan phases. At 5,000 requested files, the full-scan phase hit that cap: **only 3,012 of 5,000 files had been processed when the wait loop gave up** (`samples_processed: 3012`, `full_scan_total_ms: 626020` ≈ 10.4 min). The subsequent "incremental rescan" phase then had ~1,988 never-processed files still in the directory, so it was not actually measuring a cache-hit — it did real first-time work and *also* took ~632 s, likely also capped. The RSS and per-file numbers from this tier are reported above for completeness but should be read as "at least 3,012 files were resident," not as a clean 5,000-file data point. Re-running with a longer wait cap (or fixing the harness to not cap incremental-rescan the same way) is needed for a trustworthy 5,000+ number — not done in this pass to stay within the time budget.

### Concurrent-load caveat (N=100, N=500)

Fixture generation for the 1,000/5,000 tiers ran as a background Python process while the N=100 and N=500 `BenchmarkScan` runs were in flight (CPU contention). This affects the **timing** numbers for those two tiers (see `PERFORMANCE_BASELINE_RELEASE.md`) but not the **RSS** numbers, since RSS is read from the `BenchmarkScan` process's own `mach_task_basic_info`, unaffected by a separate process's CPU usage.

## Fixed vs. per-sample: the headline finding

**The RSS-vs-N curve is not monotonic** (N=500 → 2,286 MB is *higher* than N=1,000 → 1,907 MB), which is the key piece of evidence here. A genuine per-file leak (each processed sample permanently retaining ~3.9 MB, as Phase 1's single 2-point extrapolation implied) would produce a strictly increasing curve. This one doesn't — it jumps early and then fluctuates in a ~1.6–2.9 GB band regardless of whether N is 100, 500, or 1,000.

That pattern is consistent with a **large, mostly-fixed working-set cost** that appears once scanning starts (thread-pool worker buffers, ONNX Runtime arena allocations, CoreML compiled-graph instances — plausibly one set per worker thread, not one per file) rather than genuine linear-in-N retention.

Two numbers, both grounded in what was measured/read, not fabricated:

- **Fixed cost present at N=0 (pure init, no files): ~171 MB** (187.5 MB after init − 16.5 MB before init). This is JUCE + ONNX Runtime + CoreML EP session setup with zero data.
- **Fixed "scanning machinery" cost that appears once any batch of files is processed: roughly another ~1.4–2.1 GB**, appearing already at N=100 and not growing proportionally as N goes to 500 or 1,000. This is the dominant contributor to the multi-GB RSS Phase 1 observed — not per-file retention.
- **Genuine per-sample retained payload** (the `SampleItem` struct kept in the in-memory `samples` vector: a 512-float/2,048-byte embedding plus several `std::string`/`std::vector<std::string>` metadata fields — see `Source/SampleManagerEngine.h` lines 33–60) is structurally on the order of **2–4 KB/sample**. For 1,000 samples that's ~2–4 MB total — negligible next to the multi-GB fixed/working-set cost, and consistent with the observed curve not scaling with N in this range.

**Conclusion: this is overwhelmingly a fixed-cost story, not a per-file leak.** Phase 1's "~3.9 MB retained per file" figure was a mis-attribution — dividing a mostly-fixed working-set jump by N=500 made it look like a per-file number when the same jump appears (and doesn't grow much further) at N=100 too.

**Caveat on how far this generalizes:** the only *clean* (uncontended, fully-completed) data points are N=0 and N=1,000. The N=100/500 points are contaminated by concurrent CPU load (though RSS itself should still be trustworthy) and the N=5,000 tier didn't finish. This is enough to say confidently that the dominant cost through 1,000 files is fixed, not linear — it is **not** enough to guarantee the curve stays flat all the way to 10,000–100,000+ files. A real Instruments allocation-trace run at a completed 5,000+ and 10,000+ tier is the recommended next step before making an unbounded "handles X samples" memory claim.

## Leak investigation — no confirmed leak found

Looked for the two most likely candidates given the RSS pattern:

1. **`PendingInference::waveform`** (`Source/SampleManagerEngine.h` line 218, 160,000 floats/640 KB per in-flight file) — traced its lifecycle through `prepareFile()` → `inferenceQueue` (a `std::deque`, popped via `std::move` in `collectBatch()`, `Source/SampleManagerEngine.cpp` lines 1560–1564) → `runInferenceBatch()`. It's moved, not copied, and the batch vector goes out of scope after each batch runs. No evidence of unbounded accumulation.
2. **Computed-but-unused Mel spectrogram** (`Source/SampleManagerEngine.cpp` line 1412): `std::vector<float> melSpec = computeMelSpectrogram(audioWaveform, targetRate, frames, melBins);` is computed for every file and then never read again before going out of scope — the comment above it says "Optional features demonstration." This is **wasted CPU work, not a memory leak** (the vector is properly freed when it goes out of scope at the end of `prepareFile()`) — every file pays for a Mel spectrogram computation whose result is discarded. Flagged here as an efficiency finding worth a follow-up (deleting the dead computation would speed up per-file scan cost slightly), but **not fixed in this pass** since it's a performance note, not the memory-retention bug this section was looking for, and the task scope calls for not making speculative changes without a clear leak.

No file/path/handle leak, no unbounded cache growth, and no evidence of decoded-audio-buffer retention was found in the code paths read. **This is a code-read + memory-curve-shape finding, not an Instruments allocation-trace finding** — see "What wasn't done" below.

## What wasn't done (explicitly not measured)

- No Instruments/`leaks`/`vmmap` run was performed — RSS was read via the same `mach_task_basic_info`-based harness Phase 1 used, extended across more tiers. A full allocation-trace run (Instruments "Allocations" template, or `leaks -atExit --`) would give per-category attribution (ONNX arena vs. JUCE vs. thread stacks vs. `samples` vector) instead of the black-box RSS totals here, and is the natural follow-up if a tighter number is needed before a commercial memory claim.
- 10,000+ file tiers were not attempted, consistent with Phase 1's reasoning for not running the full ladder — the 5,000 tier already took >10 minutes and didn't finish within the harness's built-in cap.
- Database on-disk size numbers inherit the same WAL-sidecar caveat Phase 1 already documented (`db_size_bytes` readings here are similarly not fully trusted — not re-investigated in this pass).
