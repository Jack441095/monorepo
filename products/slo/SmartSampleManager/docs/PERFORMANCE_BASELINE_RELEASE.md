# SmartSampleManager — Performance Baseline (Release Build)

Phase 2 follow-up to `docs/PERFORMANCE_BASELINE.md`, which only ran Debug. Same harness (`BenchmarkScan`), same machine (Apple Silicon Mac, CoreML execution provider active), same synthetic fixtures (`generate_benchmark_fixtures.py`), this time built Release: `cmake -B build-release -DCMAKE_BUILD_TYPE=Release`, target `BenchmarkScan` (which needed `SmartSampleManager_VST3` built first in the same tree, to generate `JuceHeader.h` — a build-ordering quirk, not a product issue).

## Measured tiers

| N | Samples processed | Full scan total | Full scan ms/file | Incremental rescan | Search p50 | Search p99 |
|---|---|---|---|---|---|---|
| 0 | 0 | 0.63 ms | n/a | 0.19 ms | n/a | n/a |
| 100 | 100 | 30,353.8 ms | 303.5 ms | 523.7 ms | 0.035 ms | 0.090 ms |
| 500 | 500 | 117,940 ms | 235.9 ms | 439.9 ms | 0.052 ms | 0.106 ms |
| 1,000 | 1,000 | 222,313 ms | 222.3 ms | 493.9 ms | 0.059 ms | 0.240 ms |
| 5,000 (requested) | 3,012 (**incomplete — see below**) | 626,020 ms | 207.8 ms | 632,053 ms (**also incomplete**) | 0.00008 ms | 0.00029 ms |

**N=100 and N=500 caveat:** these two runs happened while a background Python process was generating the 1,000/5,000-file fixture directories, i.e. under CPU contention from an unrelated process. Their `ms/file` numbers are likely inflated versus a clean run and should not be read as precise. N=1,000 and the (incomplete) N=5,000 run had no concurrent load.

**N=5,000 caveat:** the harness has a hardcoded 10-minute wait cap. The full-scan phase hit it with only 3,012/5,000 files processed; the "incremental rescan" phase then had to do real first-time work on the remaining ~1,988 files (not a cache-hit measurement) and itself ran ~632 s, likely also capped. Reported for completeness, not as a trustworthy 5,000-file data point. Full detail in `docs/MEMORY_PROFILE.md`.

RSS numbers for all tiers are in `docs/MEMORY_PROFILE.md` (that document is the one asking the memory question; this one is timing/search).

## Release vs. Phase 1's Debug baseline (both at N=500, the one directly comparable tier)

| Metric | Debug (Phase 1) | Release (this pass) | Delta |
|---|---|---|---|
| Full scan, per file | 187.7 ms | 235.9 ms | **~26% slower** (but see contention caveat above) |
| Incremental rescan, total | 443.9 ms | 439.9 ms | ~same |
| Search p50 | 0.38 ms | 0.052 ms | **~86% faster** |
| Search p99 | 0.90 ms | 0.106 ms | **~88% faster** |

**Search latency improved substantially under Release, as expected** — the HNSW query path is exactly the kind of CPU-bound numeric code `-O2`/`-O3` optimization helps most.

**Full-scan per-file cost did *not* improve under Release, and the N=500 number is nominally worse than Debug.** This is a genuine anomaly worth flagging rather than explaining away: it runs counter to the usual expectation that Release builds are faster. Two honest caveats apply before reading too much into it: (1) the N=500 Release run had concurrent CPU load from background fixture generation (see above) which Debug's original run did not have; (2) even the clean N=1,000 run (222.3 ms/file, no concurrent load) is still slower than Debug's 187.7 ms/file at N=500. The likely explanation is that full-scan cost here is dominated by ONNX/CoreML inference and file I/O, not by JUCE/application CPU-bound code — the parts of the pipeline `-O2` optimization actually speeds up (search, in-memory data structure operations) did improve, while the ONNX Runtime/CoreML execution-provider cost is largely unaffected by this project's own compiler flags since it's a separately-built linked library. **Not confirmed by a controlled isolated test in this pass** — if full-scan throughput matters for a commercial claim, a follow-up run with no concurrent load, ideally with `full_scan_ms_per_file` broken down into decode vs. ONNX-inference vs. index-update sub-phases, would resolve this properly instead of relying on this single whole-pipeline number.

## What wasn't done

- 10,000+ file tiers: not attempted, same reasoning as Phase 1 (disproportionate time for a hardening pass) and confirmed by the 5,000-tier run already exceeding the harness's 10-minute cap.
- No isolated (single-run, no background contention) re-measurement of N=100/N=500 was done to remove the concurrent-load caveat — flagged above rather than silently reported as clean.
- Windows Release numbers: out of scope (this machine is macOS-only, per the task).
