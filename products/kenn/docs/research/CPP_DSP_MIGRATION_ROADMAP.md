# KENN C++ DSP Migration Roadmap

**Date:** 2026-09-20
**Recommendation:** conditional, incremental migration with measured exits.

**Current status (2026-09-20):** Phases 0 and 1 are complete. The Phase 2
scalar C++/nanobind vertical slice is integrated behind `KENN_DSP_NATIVE` and
passes the bounded WAV gate. The supplied eight-mix internal corpus now also
passes full-request parity, but the refreshed corpus averages `0.98962x` native/reference latency,
so the Python default remains the measured choice. The Apple Accelerate/vDSP
follow-up also passes parity but measures `1.00231x` on the same complete
requests, so it remains opt-in. Existing seven-track
AutoMix validation is recorded separately; it is useful technical evidence but
does not provide the exact requested stem-count matrix or rights clearance.
The historical AutoMix C++ kernel sources are now restored from `origin/main`
and compile as an isolated static archive, but they are not yet attached to
the current worker or KENN wheel. The supplied 62-stem project has now been
rendered at 1/8/16/32 stems through the preserved AutoMix entry point; all four
safety gates pass, but advisory technical scores remain below threshold and a
64-stem source is unavailable.
Phase 3 realtime-core consolidation is also passing its local numerical,
concurrency, and callback-budget checks, and universal macOS AU/VST3
packaging now passes. See
`CPP_DSP_PHASE0_RECEIPT.md`, `CPP_DSP_PHASE1_PROFILE_RECEIPT.md`,
`CPP_DSP_PHASE2_FFT_POC_RECEIPT.md`, `CPP_DSP_PHASE3_REALTIME_RECEIPT.md`,
`CPP_DSP_PHASE4_TESTING_ASSETS_RECEIPT.md`,
`CPP_DSP_PHASE4_ACCELERATE_RECEIPT.md`,
`CPP_DSP_PHASE4_REAL_MIX_PROFILE_RECEIPT.md`,
`CPP_DSP_PHASE4_NATIVE_BULK_METRICS_RECEIPT.md`,
`CPP_DSP_PHASE4_AUTOMIX_ASSETS_RECEIPT.md`, and
`CPP_DSP_PHASE4_AUTOMIX_KERNEL_RECEIPT.md`, and
`CPP_DSP_PHASE4_RELEASE_QUALIFICATION.md` for the receipts and remaining
qualification inputs.

## Phase 0 — restore a canonical product (P0, 1-3 engineering days)

### Work

- Choose `products/kenn` as the canonical product root or document another
  owner-approved root.
- Finish the interrupted 2026-09-20 migration or restore the previous layout.
- Replace/remove broken `source` and `vst3-plugin` links.
- Restore actual Python backend/plugin sources rather than `.pyc` caches.
- Make current tests and `benchmark_audio_analysis.py` import from the canonical
  tree.
- Record a source manifest/tree hash and prevent duplicate editable copies.

### Exit gate

- full product source is present;
- benchmark and plugin build commands resolve without legacy-path overrides;
- no active code imports removed `Audio_Too/studio` paths;
- current Git status/source ownership is understood.

### Rollback

Return to the pre-monorepo archive as a single read/write checkout. Do not
maintain two partly canonical trees.

## Phase 1 — benchmark and profile (P0, 2-4 days)

### Work

- Implement the JSON benchmark contract from `CPP_DSP_BENCHMARK_PLAN.md`.
- Profile complete Mix Review, bounded WAV analysis, and representative AutoMix
  projects.
- Measure stage time, peak RSS, copies, and tail latency.
- Reproduce the July AutoMix results on current source and fixtures.
- Establish numerical golden fixtures.

### Exit gate

- at least 80% of target request time is attributed to named stages;
- baseline results are repeatable within 10% median on a fresh process;
- fixtures and tolerances are checked into an appropriate test/benchmark area;
- the owner selects one bottleneck for a POC.

### Stop condition

If decoder/FFT/native candidates are below 20% of complete request time, stop
and optimize the actual bottleneck instead.

## Phase 2 — native spectral vertical slice (P1, 5-8 days)

**Bounded status (2026-09-20):** the scalar C++20 core and nanobind boundary
are implemented behind `KENN_DSP_NATIVE`. The bounded WAV gate passes with
43.3–49.7% p50 improvement, +1.37% peak RSS, and zero parity issues. Release
default remains gated on real-mix/AutoMix fixtures and cross-platform evidence.

### Scope

Port only the preserved KENN WAV analyzer's bounded PCM sample conversion,
window, FFT, power, and band-reduction hot path. Keep peak selection, qualification,
explanation, receipts, and API orchestration in Python initially.

### Work

- Create pure C++20 core and scalar reference backend.
- Add Accelerate/vDSP backend on macOS.
- Add nanobind NumPy boundary with explicit copy reporting.
- Preserve the Python implementation behind `KENN_DSP_NATIVE=0`.
- Add numerical, malformed-input, ASan/UBSan, and benchmark tests.
- Keep the Python WAV decoder as the oracle; qualify the native decoder only
  after direct parity across supported PCM widths and complete-request timing.
- Compare first with a vectorized NumPy implementation; adopt that instead if
  it meets the product gate with less complexity.

### Exit gate

- >=3x hot-stage speed-up;
- >=25% complete request improvement;
- no >5% peak-RSS regression;
- numerical and receipt parity passes;
- packaged extension works in a clean environment;
- failure falls back cleanly and visibly.

### Rollback

Default the feature flag to Python and remove the extension from packaging. No
schema or user data migration should be required.

## Phase 3 — consolidate realtime core (P1, 4-7 days)

**Local status (2026-09-20):** shared-core consolidation, callback-budget
checks, and universal macOS AU/VST3 packaging pass. Host/DAW loading matrix and
Windows x64 validation remain.

### Work

- Move/recover `AudioTooRealtimeCore` into the shared core without changing the
  plugin's pass-through behaviour.
- Precompute filter coefficients in `prepare()` rather than per block.
- Decide whether display-only atomics are sufficient or add a sequence-stamped
  coherent snapshot.
- Correct evidence names: do not map peak to true peak or RMS to LUFS.
- Link the JUCE plugin statically to the core.
- Re-run numerical parity, 32-2048 buffer performance, host-layout tests, TSan,
  and DAW smoke tests.

### Exit gate

- p99.9 under 20% of the smallest supported callback deadline;
- zero allocations/locks/I/O in callback;
- transparent pass-through is bit-identical where expected;
- VST3 and AU load on supported macOS hosts;
- Windows VST3 plan is tested before claiming Windows support.

### Rollback

Disable analysis or ship the prior side-loaded plugin binary. The companion and
offline path must remain usable without the plugin.

## Phase 4 — recover proven AutoMix kernels (P2, 5-10 days)

### Work

- Recover limiter, smoothing, reverb, EQ, saturation, and transient-threshold
  sources from the preserved audio-analysis tree.
- Verify which are actually called in the canonical runtime.
- Reproduce fuzz/parity tests against Python/Numba/SciPy.
- Rebuild in CI instead of compiling on demand at runtime.
- Keep the phase-correlation C++ implementation disabled unless its algorithm
  changes and beats the FFT reference.
- Evaluate batching and avoided round-trips before adding any new kernel.

**Recovery note (2026-09-20):** the historical AutoMix audit records these
measurements and parity checks, but the current checkout has no recoverable
AutoMix C++ source or worker implementation. Treat the results as a prioritized
recovery list, not as current release evidence; see
`CPP_DSP_PHASE4_AUTOMIX_KERNEL_RECEIPT.md`.

### Exit gate

- >=10% complete representative AutoMix improvement;
- no render-quality or qualification regression;
- every native kernel has a reference, fuzz/parity test, and fallback;
- per-platform packaged builds and notices are complete.

### Stop condition

Do not retain marginal kernels merely because they exist. A 1.0x result should
use the simpler reference path unless reuse/realtime constraints justify it.

The zero-lag correlation POC followed this rule: despite a faster isolated
loop, its 9.0–10.1% complete-request gain did not clear the 25% gate and the
temporary binding was removed. See `CPP_DSP_PHASE4_CORRELATION_POC_RECEIPT.md`.

## Phase 5 — cross-platform release engineering (P1, 5-10 days)

### Work

- macOS arm64/x86_64 and supported Windows x64 CI;
- signed/notarized plugin and companion artifacts;
- Python wheel matrix for supported Python versions;
- dependency/SBOM/licence review;
- crash symbols and implementation-version diagnostics;
- real Ableton sessions at several sample rates/buffer sizes;
- bounded soak, project reload, and plugin state compatibility tests.

### Exit gate

- clean-machine install and uninstall;
- plugin validation and host matrix pass;
- fallback works when the extension is absent;
- performance claims are reproduced on both target platforms;
- support runbook identifies native backend/version from a receipt.

## Deferred work

- GPU DSP acceleration;
- browser/WebAssembly DSP;
- custom model inference runtime;
- full AutoMix rewrite;
- C++ retrieval/orchestration;
- new realtime audio processing in the transparent KENN assistant plugin.

These require a new profile and product decision, not an extension of this
roadmap.

## Resourcing estimate

One senior C++/DSP engineer plus a Python engineer familiar with the existing
qualification contracts can complete Phases 0-3 in roughly 3-5 focused weeks,
including review and measurement. Phase 4 depends heavily on how much preserved
AutoMix source can be canonically recovered. Cross-platform release work can
add another 1-2 weeks and should not be compressed into the POC.

## Owner decisions required

1. Confirm the canonical post-migration KENN source root.
2. Confirm supported platforms and Python versions.
3. Confirm JUCE licence position and whether Windows is a beta requirement.
4. Approve the first POC only after Phase 1 profiles select it.
5. Decide whether offline spectral analysis or AutoMix throughput is the first
   user-visible performance goal.
