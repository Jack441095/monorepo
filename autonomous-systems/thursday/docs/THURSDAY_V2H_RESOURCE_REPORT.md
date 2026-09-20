# Thursday V2-H Resource Report

## Scheduling policy

* Heavy specialist tasks are capped at **2 concurrent** (`HEAVY_TASK_LIMIT`);
  the reconciler enforces the budget strictly (Z-40) and defers excess work.
* Newly unblocked work is surfaced to the owner but never auto-executed —
  each cycle is deliberate, bounding runaway feedback loops.
* Diagnostics are bounded: 100 retained failures / 50 MB total / 7-day age /
  1 MB per entry; oversized entries are refused (Z-23, Z-35).

## Soak (5,000 simulated workflow cycles)

Machine artifact: `thursday/evals/THURSDAY_V2H_SOAK_RESULTS.json`
(runner: `thursday/evals/v2h_soak.py`, seed 20260823).

| Metric | Value |
|---|---|
| Total workflows | 5,000 |
| Total operations | 66,495 |
| Errors | 0 |
| Invalid state transitions accepted | 0 |
| Orphan tasks | 0 |
| Stale leases accepted | 0 (3,414 correctly rejected) |
| Duplicate side effects accepted | 0 (3,414 replay attempts blocked) |
| Rollback failures | 0 (1,707 drills executed) |
| Scope escapes undetected | 0 |
| Unsupported claims accepted | 0 |
| Latency p50 / p95 / p99 / max | 0.024 / 10.6 / 37.9 / 267.7 ms |

## Memory

RSS baseline 25.4 MB → end 21.2 MB → peak 26.0 MB · drift **−4.13 MB**.
No monotonic growth across 5,000 cycles.

## Environment caveat

The soak ran while multiple unrelated NITE DSP agent processes were active
(host load average ≈ 84 at start). Throughput (≈264 cycles/s) and tail
latencies are therefore **CONTESTED** and should not be read as clean
benchmarks. Functional integrity results are unaffected: all counters are
deterministic assertions, not timing-dependent.

No foreign processes were signalled, reniced, or paused during qualification.
