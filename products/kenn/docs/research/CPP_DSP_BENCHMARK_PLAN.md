# KENN C++ DSP Benchmark Plan

**Date:** 2026-09-20
**Purpose:** produce reproducible evidence before any native migration is
accepted.

## Baseline status

The Phase 0 source blocker is cleared. The active Python reference now emits a
`kenn.dsp_benchmark.v1` receipt with source revision, machine metadata, fixture
hashes, raw samples, p50/p95/p99 latency, peak RSS, and a qualified verdict.
The first Phase 1 run is recorded in
`results/phase1_audio_analysis_benchmark.json`; the cProfile stage receipt is
`results/phase1_audio_analysis_profile.json`.

The bounded Phase 2 native comparison is recorded in
`results/phase2_native_comparison.json`. The scalar C++/nanobind path clears
the bounded request gate, but the release-default decision remains pending a
real-mix fixture pack and cross-platform packaging evidence.

The active product previously could not run its full audio-analysis benchmark:
`tooling/scripts/benchmark_audio_analysis.py` imports a backend module that is
missing from the active monorepo boundary. This is a benchmark blocker and a
source-migration defect, not evidence that C++ is required.

Two bounded measurements are available:

1. Active `mix-review/qualified_detectors.py` detector-only timing:

   | Duration | p50 | p95 | Runs |
   | ---: | ---: | ---: | ---: |
   | 1 s | 0.355 ms | 0.387 ms | 50 |
   | 10 s | 2.883 ms | 2.935 ms | 30 |
   | 60 s | 17.735 ms | 18.290 ms | 12 |
   | 180 s | 54.771 ms | 54.846 ms | 5 |

2. Preserved archived realtime binary on Apple M3 at 48 kHz:

   | Buffer | ns/sample | Realtime budget |
   | ---: | ---: | ---: |
   | 64 | 14.788 | 0.071% |
   | 128 | 9.347 | 0.045% |
   | 256 | 8.811 | 0.042% |
   | 512 | 8.704 | 0.042% |
   | 1024 | 8.637 | 0.041% |

The first is current source but excludes decode. The second is current-machine
execution but uses a preserved binary. Neither is a complete active-product
baseline.

## Phase 0: make the baseline legitimate

Before comparing implementations:

1. choose and document the canonical KENN source root;
2. repair/remove the broken `source` and `vst3-plugin` links;
3. make `benchmark_audio_analysis.py` import from that root;
4. record the exact source revision or tree hash;
5. pin dependencies and record compiler/CMake options;
6. make all benchmark output machine-readable JSON;
7. keep generated fixtures and results outside source packages.

No C++ candidate passes a gate while the reference path is unresolved.

## Workload matrix

### Audio formats

- PCM WAV: 16-, 24-, and 32-bit integer; 32-bit float;
- mono and stereo;
- 44.1, 48, 88.2, 96, and 192 kHz;
- durations: 1 s, 10 s, 60 s, 10 min;
- buffer sizes for realtime: 32, 64, 128, 256, 512, 1024, 2048;
- non-WAV formats only when the production decoder supports them.

### Signals

- silence and denorm-prone very-low-level sine;
- DC, impulse, full-scale and clipped plateaus;
- bin-centred and off-bin sine sweeps;
- pink/white noise with deterministic seeds;
- anti-phase, mono, hard-panned, and intentionally asymmetric stereo;
- transient trains and dense program material;
- at least five licensed or internally owned real mixes;
- 1, 8, 16, 32, and 64-stem projects for AutoMix.

### Stages

Instrument these separately and end to end:

1. file read and hash;
2. container decode and sample conversion;
3. channel/layout conversion;
4. resampling;
5. window creation/application;
6. FFT/STFT and magnitude/power conversion;
7. band reductions and feature aggregation;
8. loudness/true-peak analysis where present;
9. qualified detectors;
10. AutoMix stem preparation, analysis, planning, DSP render, validation, and
    export;
11. binding/ABI crossing and result conversion;
12. complete user-visible request.

## Metrics

For offline cases record:

- warm and cold wall time;
- p50, p95, p99 and maximum latency;
- audio seconds processed per wall second;
- CPU time and effective core utilization;
- peak RSS and bytes copied where measurable;
- allocation count/bytes for owned native workspaces;
- cache hit/miss state;
- stage contribution to total latency;
- output hash and numerical error against reference.

For realtime cases record:

- average, p95, p99, p99.9 and maximum callback time;
- callback time as a percentage of buffer deadline;
- allocations, locks and syscalls in callback;
- underruns/dropouts under synthetic host load;
- sanitizer results;
- CPU architecture and SIMD path selected.

Do not compare Debug Python to Release C++. Native candidates use `Release`
with symbols retained for profiling. Report all flags; do not use `-ffast-math`
unless a separate accuracy review explicitly approves it.

## Candidate comparisons

### POC A: KENN bounded WAV spectral path

Compare:

- preserved Python reference;
- vectorized NumPy/`numpy.fft.rfft` implementation;
- C++20 portable scalar/SIMD backend;
- Accelerate/vDSP backend on macOS;
- JUCE FFT only as a portability baseline.

This ordering tests whether an algorithm/library substitution solves the issue
without creating a product-owned C++ kernel.

### POC B: AutoMix recovered kernels

For each recovered kernel compare:

- Python/NumPy/SciPy or Numba reference;
- native kernel alone;
- complete stage;
- complete 1/8/16/32/64-stem project.

A kernel microbenchmark is insufficient. A fast kernel that contributes 2% of
the request cannot justify a migration.

### POC C: offline shared feature core

Measure the same core through:

- direct C++ test executable;
- nanobind with a contiguous float32 NumPy view;
- nanobind with conversion-required inputs;
- plugin static linkage.

This reveals binding/copy cost and prevents a misleading kernel-only claim.

## Statistical procedure

1. Disable unrelated heavy jobs and record power/thermal state.
2. Run one unreported warm-up for steady-state cases.
3. Randomize candidate order to reduce thermal/order bias.
4. Run at least 30 repetitions for sub-second cases and 10 for longer cases.
5. Retain raw samples, not only aggregates.
6. Report median and tail latency; do not select the best run.
7. Repeat the winning comparison in a fresh process.
8. Repeat on Apple Silicon and the supported Windows x64 baseline before
   shipping a cross-platform claim.

## Numerical acceptance

Each metric gets an explicit contract. Initial proposed bounds:

| Output | Acceptance |
| --- | --- |
| Sample peak/RMS | <= 1e-6 linear or <= 0.001 dB away from reference |
| Correlation/width | <= 1e-5 absolute |
| FFT magnitudes | relative/absolute tolerance defined per window and floor; verify Parseval energy |
| Dominant frequency | <= half-bin error relative to the configured FFT |
| Band energy | <= 0.05 dB for normal-energy bands |
| Resampling | impulse/frequency-response suite plus alias rejection and latency declaration |
| True peak | <= 0.05 dB against the chosen qualified reference |
| Loudness | <= 0.1 LU against the chosen qualified reference |
| Detector receipt | exact gate action/status and schema; numeric values within declared tolerance |
| Render | null/difference metrics plus owner-approved listening gate |

NaN, Inf, empty buffers, odd lengths, truncated containers, non-contiguous
arrays, and unsupported layouts must fail deterministically.

## Performance acceptance and rollback

A native offline POC is adopted only when all are true:

- >=3x faster than the reference for its isolated hot stage;
- >=25% faster for the complete target request, or >=10% for a complete
  AutoMix project when the stage is only one component;
- no worse than 5% peak-RSS regression unless explicitly justified;
- binding/copy overhead is included;
- all parity, receipt, and failure-contract tests pass;
- Python reference/fallback remains selectable;
- build and package succeed on every supported target.

The realtime core passes only when:

- p99.9 callback time remains below 20% of the smallest supported deadline;
- zero callback allocations and blocking locks are demonstrated;
- numerical parity and sanitizer suites pass;
- feature-disabled mode remains transparent pass-through.

Rollback triggers:

- parity failure;
- crash or host instability;
- tail-latency regression;
- missing wheel/plugin architecture;
- a complete-request speed-up below the acceptance threshold;
- licence or distribution uncertainty.

Rollback is the feature flag for offline Python and removal/disablement of the
side-loaded plugin analysis feature for realtime. Never delete the reference
implementation during qualification.

## Required result artifact

Every run should emit:

```json
{
  "schema": "kenn.dsp_benchmark.v1",
  "source_revision": "tree-or-commit-id",
  "candidate": "python|numpy|cpp-scalar|vdsp|juce",
  "build_type": "Release",
  "compiler_flags": [],
  "machine": {},
  "fixture": {},
  "stage_samples_ms": [],
  "peak_rss_bytes": 0,
  "numerical_comparison": {},
  "selected_simd_backend": "",
  "passed": false
}
```

Raw results should be retained under a dated benchmark-results directory and
summarized in this research set only after reproduction.
