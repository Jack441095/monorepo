# PX-F - Plugin Performance & Interaction Report

## Status

**PASS WITH LIMITATIONS**

Budgets were created and two isolated benchmark families ran. The result is a useful performance contract, not a production qualification.

## Required Closeout

### PERFORMANCE BUDGET

**Created.** The full machine-readable manifest is [performance_budget_manifest.json](../performance/performance_budget_manifest.json). It defines target, stretch, and fail values for open, first paint, search, filters, MAP frames, audition start, drag initiation, IPC, background analysis, and scan UI responsiveness.

Recommended headline budgets:

| Surface | Target | Stretch | Fail |
|---|---:|---:|---:|
| Search response | 50 ms | 20 ms | 200 ms |
| MAP P95 frame | 16.7 ms | 8.3 ms | 33.4 ms |
| Warm audition start | 100 ms | 50 ms | 250 ms |
| IPC P95 | 5 ms | 2 ms | 20 ms |
| Background analysis UI block | 0 ms | 0 ms | 16.7 ms |

### MAP

The synthetic 25,000-point proxy measured 11.9241 ms median for a full scan and 0.3452 ms for cell culling at a 4% viewport, with identical visible counts. Existing SLO source evidence shows cached static layers and QuadTree queries. Next validation must capture P95/P99 and frame spikes in JUCE with labels, hover, selection, and animation active.

### SEARCH

The synthetic 25,000-record proxy measured a worst-query median of 241.9812 ms for the observed linear scan and 6.4816 ms for exact-token lookup. The candidate changed numeric substring semantics, so speed alone is insufficient. The target is a semantics-preserving index, not exact-token behavior at any cost.

### IPC

The existing AI Platform `LocalRuntime` was measured over a temporary owner-only Unix socket for 100 `company.brief.daily` requests:

- Median: **0.5481 ms**.
- P95: **16.3472 ms**.
- Maximum: **131.4537 ms**.
- Socket mode: **0600**.

The median is healthy; the tail requires cold-start, concurrency, and host-load testing before a hard interactive promise.

### MULTI-INSTANCE

No production multi-instance benchmark was run. The platform design explicitly aims for one shared model copy in the local runtime, while the SLO plugin currently owns its own process-local state. Measure 1, 3, and 10 instances for model memory, database contention, worker count, and shutdown before choosing an ownership model.

### AUDIO THREAD

The audited SLO `processBlock` keeps file preparation off the callback and performs bounded playback work. Two real code risks remain: `dawBpm`/`isDawPlaying` are shared without atomic synchronisation, and pending reader/trigger handoff is not protected by an explicit lock-free publication primitive. This is an engineering follow-up, not a reason to claim the audio thread is unsafe overall.

## Biggest Performance Risk

The biggest risk is tail behavior hidden by good medians: IPC spikes, cold model initialization, and future cross-product calls accidentally entering a real-time or UI-critical path.

## Failure Experience

Test and specify model unavailable, local runtime down, database unavailable, interrupted scan, corrupt/unsupported file, timeout, and permission failure. Every failure must preserve the current selection and tell the user the next recoverable action.

## Promotion Decision

Adopt the budget shape in performance reviews. Promote production-shaped instrumentation and audio-thread publication fixes. Continue R&D on cold-start, multi-instance, JUCE frame traces, and failure recovery.

## Artifacts

- [search_and_map_results.json](../benchmarks/search_and_map_results.json)
- [ipc_benchmark.py](../benchmarks/ipc_benchmark.py)
- [ipc_results.json](../benchmarks/ipc_results.json)
- [performance_budget_manifest.json](../performance/performance_budget_manifest.json)
