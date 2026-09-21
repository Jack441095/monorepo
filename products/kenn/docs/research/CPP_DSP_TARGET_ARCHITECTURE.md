# KENN C++ DSP Target Architecture

**Date:** 2026-09-20
**Status:** native spectral POC implemented behind the optional nanobind
boundary; production default remains gated on representative real-mix
fixtures and cross-platform release evidence.

## Architecture decision

Use C++ only as a small deterministic audio engine. Keep product policy and
workflow in Python.

```text
Ableton / DAW audio callback
        |
        v
JUCE plugin ------------------------------+
  processBlock()                           |
  preallocated realtime state              |
        | static link                       |
        v                                   |
  libkenn_dsp_core (C++20)                 |
        | POD FeatureFrame                  |
        v                                   |
 lock-free/sequence snapshot                |
        | non-audio worker                  |
        +----> versioned evidence JSON ---->+----> Python KENN companion

Local file / stems
        |
        v
Python container orchestrator
        |
        +---- Python decoder (reference)
        |
        +---- optional nanobind PCM decoder (`KENN_DSP_NATIVE=1`)
        |
        | contiguous float32 NumPy view
        v
nanobind adapter -> libkenn_dsp_core -> typed result -> Python receipt/policy
        |
        +---- feature flag ---- Python reference fallback
```

The plugin and Python extension share algorithms by linking the same pure core;
they do not call one another. Python, JSON, networking, and model work never
enter the callback.

## Proposed source layout

After the monorepo migration is repaired:

```text
products/kenn/
  tooling/native/dsp_core/
    CMakeLists.txt
    fft_core.hpp
    kenn_dsp_native.cpp
  native/
    CMakeLists.txt
    include/kenn/dsp/
      types.hpp
      realtime_analyzer.hpp
      spectral_analyzer.hpp
      version.hpp
    src/
      realtime_analyzer.cpp
      spectral_analyzer.cpp
      backend_scalar.cpp
      backend_accelerate.mm
    python/
      bindings.cpp
    tests/
      test_numerical_parity.cpp
      test_realtime_safety.cpp
      test_performance.cpp
  plugins/kenn-vst3-au/
  apps/backend/src/kenn/
  tooling/benchmarks/
```

The current POC lives under `tooling/native/dsp_core` while it is being
validated. Consolidating it into the long-term `native/` layout is a packaging
task after the complete-request and platform gates pass.

JUCE belongs in the plugin target. The core should use the standard library and
small backend interfaces so offline analysis does not acquire a JUCE runtime or
licensing dependency unnecessarily.

## Core interfaces

### Offline view

The core accepts caller-owned contiguous float32 planar or interleaved audio.
It does not own files, decode containers, allocate Python objects, or serialize
JSON.

```cpp
struct AudioView {
    const float* data;
    std::uint64_t frames;
    std::uint32_t channels;
    std::uint32_t stride;
    double sample_rate;
    Layout layout;
};

struct SpectralConfig {
    std::uint32_t fft_size;
    std::uint32_t hop_size;
    Window window;
    std::uint32_t max_windows;
};

struct SpectralResultView {
    // Caller-provided result buffers/spans.
};

Status analyze_spectral(
    AudioView input,
    const SpectralConfig& config,
    SpectralWorkspace& workspace,
    SpectralResultView output) noexcept;
```

Rules:

- sizes use fixed-width types and are bounds-checked;
- ownership remains with the caller;
- no exception crosses the module boundary;
- output buffers and workspaces are reusable;
- configuration is immutable during a call;
- unsupported layout returns a typed error;
- results include algorithm/backend/version identifiers.

### Realtime state

`prepare()` creates plans, coefficients, windows, and scratch storage. `process()`
is bounded and `noexcept`.

```cpp
class RealtimeAnalyzer final {
public:
    Status prepare(const RealtimeConfig&, RealtimeWorkspace&) noexcept;
    void reset() noexcept;
    void process(const float* const* channels,
                 std::uint32_t channel_count,
                 std::uint32_t frames) noexcept;
    bool snapshot(FeatureFrame& out) const noexcept;
};
```

If coherent multi-field frames are required, publish a double-buffered or
sequence-stamped `FeatureFrame`; do not add a mutex. Atomics-per-metric remain
acceptable for display-only metering.

## Python boundary

Use a thin nanobind module for offline calls:

- require/fast-path C-contiguous float32 arrays;
- reject invalid dimensionality and absurd sizes before entering C++;
- expose whether a conversion/copy occurred;
- release the GIL around long pure-native work;
- retain Python ownership for the full native call;
- return small typed results or fill caller-owned NumPy buffers;
- translate native status codes to specific Python exceptions;
- package wheels per supported Python/macOS/Windows architecture.

Do not make thousands of per-window or per-sample Python/native calls. Cross
the boundary once per analysis batch.

The internal C++ API need not promise a stable binary ABI because the plugin
and extension are built together. If third-party/process boundaries are added
later, put an explicitly versioned C ABI over the core rather than exposing C++
STL types.

## Backend strategy

Backend selection is compile-time plus safe runtime capability detection:

1. Accelerate/vDSP on macOS for the first POC;
2. portable scalar/reference backend for parity and fallback;
3. compiler auto-vectorization/NEON or xsimd/Highway only after profiling;
4. Windows backend selected after benchmark (for example oneMKL or a suitable
   permissive implementation);
5. JUCE FFT as a portability baseline, not an assumed performance winner;
6. FFTW excluded by default because of GPL/commercial licensing implications.

Every backend must produce the same contract within declared tolerance. Record
the selected backend in receipts and benchmark results.

## Feature and evidence contract

C++ produces measurements; Python assigns product meaning.

```text
Native MeasurementFrame
  schema/version
  algorithm/backend/version
  sample rate, channels, frames/window
  sample peak, RMS, correlation, band powers, spectral peaks
  validity flags and numerical warnings

Python Evidence/Receipt
  source hash and provenance
  scope and freshness
  qualified detector/gate result
  explanation and suggested next step
  limitations
```

The native core must not label RMS as LUFS or sample peak as true peak. Those
names require their actual standards-compliant algorithms and qualification.

## Realtime safety contract

Inside the callback:

- no heap allocation or deallocation;
- no filesystem, network, database, IPC, JSON, model, or Python call;
- no blocking mutex, condition variable, or wait;
- no logging or error-string construction;
- no exception propagation;
- no FFT-plan or filter-coefficient creation;
- no unbounded iteration;
- no destruction with unpredictable cost;
- handle denormals and non-finite input deterministically;
- preserve transparent audio pass-through unless a separately qualified DSP
  feature explicitly processes audio.

All UI/handoff work consumes snapshots on a non-audio worker. The queue is
bounded, may drop stale meter frames, and cannot back-pressure `processBlock()`.

## Threading and batch analysis

Offline parallelism should be outside individual simple kernels:

- schedule independent stems with a bounded pool;
- avoid nested BLAS/FFT/thread-pool oversubscription;
- cap worker count from measured memory per stem;
- share immutable plans where the backend permits it;
- use one feature pass/cache per source hash and analysis profile;
- preserve deterministic result order and seeds.

GPU acceleration is not in the initial design. KENN's reductions and modest
FFT windows are likely too small to amortize transfers. Reconsider only after a
profile shows sustained, batchable work and includes transfer time.

WebAssembly is also out of scope because current KENN audio work is local
native/Python/DAW work, not browser-resident DSP.

## Build and packaging

- CMake 3.22+ and C++20, matching the preserved plugin baseline;
- `Release` and `RelWithDebInfo` presets;
- arm64 and x86_64 macOS plugin bundles as required by supported hosts;
- signed/notarized plugin and companion artifacts;
- platform wheels for the Python extension;
- ASan/UBSan test jobs and TSan for applicable concurrency targets;
- no runtime compilation of production kernels;
- software bill of materials and third-party notices;
- reproducible version strings embedded in native and Python artifacts.

Avoid the preserved on-demand `ctypes` compiler pattern for a commercial
release. It complicates code signing, compiler availability, cache ownership,
and failure diagnosis. Compile and package native artifacts in CI.

## Failure and rollback

- `KENN_DSP_NATIVE=0` forces the Python reference implementation.
- Missing/incompatible extension falls back with a structured diagnostic.
- Native numerical warnings never become confident product findings.
- A native crash is isolated from batch jobs where practical; the DAW plugin
  keeps the realtime core especially small because it runs in the host process.
- Results state the implementation/backend used.
- Reference code remains until at least two release cycles of cross-platform
  evidence pass.

## Security and privacy

The core accepts memory supplied by the local host and emits measurements. It
does not open paths, connect to sockets, retain raw audio, or load plugins. The
Python owner preserves KENN's local-only, no-audio-upload boundaries.
