# KENN Phase 4 Native Spectral-Peak Receipt

**Run date:** 2026-09-21
**Status:** qualified as an opt-in report-path optimization

The native spectral call now emits the aggregate and per-window dominant-peak
records directly from the C++ power arrays. This removes the Python local-max,
parabolic-interpolation, bandwidth, and confidence scan from the hot report
path. If the fields are absent (for example, an older optional wheel), the
Python `_dominant_peaks` implementation remains the fallback.

Verification:

- Native and forced-reference complete reports match for metrics, findings,
  dominant peaks, localized peaks, and 40-band LTAS rows.
- The same exact comparison passes for three seeded random PCM fixtures at
  both 44.1 kHz and 48 kHz.
- The native smoke checks peak output through the wheel contract.
- Native backend audio-analysis tests pass (11 tests); the forced reference
  path also passes all 11 tests.
- On the deterministic 10-second, 48 kHz fixture, the warm native p50 was
  `4.060 ms` with peak extraction enabled in the C++ call. The corresponding
  forced-reference p50 was `241.981 ms`; the benchmark includes decoding,
  spectral processing, and report construction, not just peak extraction.
- The refreshed cProfile no longer records Python `_dominant_peaks` calls in
  native mode; remaining time is report orchestration and the binding boundary.

This is bounded synthetic runtime evidence. Keep native dispatch opt-in until
rights-cleared real-mix, cross-platform, and complete AutoMix qualification
gates are satisfied.
