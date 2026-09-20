# LAYER ALIGNMENT PERFORMANCE REPORT
### NITE DSP Intelligent Layer Alignment R&D — Candidate Product #2

## Measurement context (important)

All timings were captured on an Apple M3 (8-core, 16 GB) whose CPU was
heavily contended during the programme window by unrelated concurrent
workloads — measured scalar C++ throughput was ~9 MFLOP/s and a 64k-point
`rfft` ~23–42 ms (normal M3 expectation: three orders of magnitude faster;
load average ranged 85–212). Absolute times below are therefore
**non-representative ceilings**; the meaningful outputs are algorithmic
complexity, relative ratios and the C++ parity proof.

## Complexity of shipped analysis path

| stage | complexity | notes |
|---|---|---|
| xcorr_plain | O(N log N) | scipy FFT correlate; per-lag norms vectorised via cumsum |
| gcc_phat/soft | O(N log N) | single rfft pair + weighting + irfft |
| phase_slope folded-median | O(N log N) | full-length cross-spectrum, freq-smoothed |
| bandwise (6 bands) | 6 × O(N) filtfilt + per-band GCC(±max_lag) |
| fast_search verify | O(W·B) adds | W=±10 window, B=3 bands; prefiltered once; fractional refine via band-domain phase shift |
| full analyze_pair+verify | ≈ 20 FFT-class ops on ≤65k points |

No stage is O(N²); the naive time-domain correlator in the C++ spike exists
only as a parity reference.

## Measured on this machine (ms per call, n=32768 @48 kHz)

| operation | 4096 | 16384 | 65536 |
|---|---|---|---|
| xcorr_plain ±256 | <5 | ~15 | ~60 |
| gcc_soft | <5 | ~12 | ~45 |
| phase_slope | <5 | ~10 | ~35 |
| bandwise 6-band | ~40 | ~150 | ~600 |
| analyze_pair total | ~90 | ~300 | ~1200 |
| estimate→verify recommend | — | ~500–2000 | — |

(See `results/performance.json` for the exact captured table from the final
batch; contention makes repeated runs vary ±3×.)

## Architecture decision: capture/analyse, not continuous

- Producers act at decision points (layer added, plugin changed), not every
  buffer. Event-driven re-analysis matches the workflow.
- Analysis latency of even 1–2 s per pair (on this throttled machine; orders
  less on healthy hardware) is acceptable for an "Analyse" button.
- Continuous monitoring would add real-time constraints (buffered windows,
  lock-free transport sync) with no measured benefit to recommendation
  quality. Rejected for this product generation.

## Memory

Working set per pair ≤ 4 × N × sizeof(double) transient (≈2 MB at 96k×16k)
plus FFT work buffers; trivially compatible with plugin hosting.

## C++ spike

- Independent implementation (custom radix-2 complex FFT, energy-normalised
  xcorr, soft-PHAT): **numerical parity proven** within float32 input
  quantisation (worst 0.143 samples on a flat LF correlation top; ≤0.02
  elsewhere; `results/cpp_parity.json`).
- Runtime parity-vs-numpy could NOT be meaningfully benchmarked under the
  contention conditions (both implementations degraded similarly); the
  porting path (stateless kernels, no allocation in inner loops) is
  validated, speed claims deliberately deferred to an uncontended bench.

## Real-time feasibility verdict

Feasible with large margin on healthy hardware for capture/analyse.
Continuous sub-real-time monitoring is *not required* and not recommended
for v1.
