# KENN Phase 4 AutoMix Native Dispatch Receipt

**Run date:** 2026-09-21
**Status:** opt-in binding smoke passes; full AutoMix promotion remains open

The recovered AutoMix kernels are now compiled into the same optional
nanobind extension as KENN's spectral, metrics, and PCM-decoder kernels. The
new `kenn.core.automix_native` adapter preserves the existing Python path and
returns `None` when `KENN_DSP_NATIVE=0` or the extension cannot load.

Exposed kernels:

- peak-follower limiter with gain envelope;
- SOS biquad filtering;
- direct phase correlation;
- attack/release smoothing and gate envelope;
- rolling median/MAD transient threshold.

Evidence completed on the local macOS arm64 build:

- CMake Release nanobind builds pass with Accelerate enabled and with the
  portable scalar backend (`KENN_USE_ACCELERATE=OFF`);
- installed-wheel smoke passes through `tooling/scripts/test_native_dsp.py`;
- deterministic identity-biquad, inverted-signal correlation, finite-output,
  shape, and limiter contract checks pass;
- backend audio-analysis tests pass in native mode (10 tests) and with
  `KENN_DSP_NATIVE=0` (10 tests), and the standalone reference fallback smoke
  passes;
- wheel build and isolated target-directory install smoke pass.

This receipt does not claim complete AutoMix request parity: the current
checkout has recovered kernel sources but not the active Python AutoMix worker
implementation needed to wire each operation into a real request. The
available `testing-assets` manifest is also labelled `TODO-vendor-pack`, so it
cannot clear the rights-gated real-mix matrix. Keep the adapter opt-in until a
rights-cleared corpus, full-request parity/performance comparison, Windows
wheel run, and host validation are complete.
