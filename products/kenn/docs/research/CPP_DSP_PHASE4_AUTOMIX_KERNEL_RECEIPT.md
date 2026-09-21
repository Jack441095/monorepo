# KENN Phase 4 AutoMix Kernel Recovery Receipt

**Run date:** 2026-09-20
**Status:** source recovered and standalone compile passes; runtime integration
and full-request requalification still required

`Audio_Too/docs/audits/2026-07-30-automix-cpp-kernel-and-vectorization-pass.md`
records a real-track AutoMix optimization pass. It reports bit-identical
fuzz/real-audio checks and measured improvements for the following kernels:

| Kernel | Historical result | Current decision |
| --- | --- | --- |
| Peak-follower limiter and release smoothing | 1.04–1.50× vs Numba/scipy | Recover and remeasure |
| Compressor/gate smooth envelope | 1.06–1.55× | Recover and remeasure |
| Fused Schroeder reverb | 1.26× | Recover and remeasure |
| Rolling median/MAD transient threshold | Part of a 2.03×/3.49× detector win | Recover and remeasure |
| EQ biquad SOS filter | 1.03× | Recover only if integration cost is low |
| Reverb primitives | ~1.00× | Do not prioritize |
| Saturator waveshaping | ~1.00× | Do not prioritize |
| Direct phase correlation | 0.20× (5× slower) | Keep disabled; FFT path wins |

The same audit attributes the largest end-to-end gains to algorithmic changes,
not the language switch alone: avoiding a WAV encode/reparse round trip,
vectorizing ERB accumulation and batched FFT work, and fusing limiter passes.
It reports `dream_of_you` falling from 50.8 s to 22.6 s and a `stranger`
render-loop stage falling from 68.9 s to 51.5 s on that historical harness.

## Recovery boundary

The nine C++ source files under
`audio-technology/audio-analysis/audio_analysis/dsp_engine/native/` have now
been restored byte-for-byte from the `origin/main` commit (`f4a90d2`). A
standalone `clang++ -std=c++17 -O3 -fPIC -Wall -Wextra -Werror` build of every
kernel and a static archive link both pass. A universal macOS archive also
contains both `arm64` and `x86_64` slices; see
`results/phase4_automix_kernel_recovery.json`.

The archive now also has a deterministic CTest link/runtime smoke. It calls the
recovered EQ, limiter, smoothing/gate, transient-threshold, reverb, saturator,
and direct-correlation exports, checks finite output, and verifies the zero-lag
identical-signal correlation path.
That smoke passes locally and is run in the native CI workflow; it proves the
archive is callable, not that any kernel is suitable for AutoMix dispatch.
The same link/runtime smoke also passes under ASan/UBSan locally and is
scheduled in the Unix sanitizer CI job.

The sources are not yet attached to the current AutoMix Python worker or the
KENN native-wheel build. These historical numbers therefore cannot be used as
current release claims. The next implementation step is to recreate the
Python/native dispatch boundary, preserve the current reference path, and
rerun parity plus complete-request benchmarks against the supplied
`testing-assets` corpus.

The current KENN scalar spectral POC remains separately qualified for parity,
but its refreshed full-request result on the eight supplied mixdowns is `0.98962x`.
Until the historical kernels are recovered and reproduced, keep the Python
AutoMix path and the opt-in native spectral flag unchanged.
