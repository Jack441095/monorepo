# KENN C++ mega-optimization pass receipt

## Scope

This pass followed the full optimization prompt across the active KENN DSP
paths. It re-profiled the Python reference, the existing optional C++/vDSP
path, Mix Review loudness, native decoding, masking, and the recovered
AutoMix kernel archive.

The measured implementation work was:

- native Mix Review K-weighting/LRA/true-peak processing;
- reusable true-peak workspaces and prefix-sum gated loudness windows;
- opt-in native Mix Review WAV decoding with float32 preservation; and
- existing C++ spectral, LTAS, masking, channel-statistics, and decoder paths
  revalidated against real 24-bit assets.

The recovered `audio-technology/.../dsp_engine/native` archive also builds and
passes its link smoke test, but its active Python AutoMix worker sources are
not present in this checkout. It remains a recovery boundary and was not
wired into production code without a complete-request parity target.

## Synthetic baseline

On the deterministic 10-second stereo PCM16 Mix Review fixture (48 kHz,
SHA-256 `5e6545d28a2ea8f39e6b5600bf603850cc7c848412dc27baba359307b4ae61b7`):

| Path | p50 complete request | Parity |
| --- | ---: | --- |
| Python pyloudnorm/scipy | 81.705 ms | oracle |
| C++ native decode + loudness + true peak | 13.580 ms | exact |

The current candidate is 83.4% lower p50 latency. It remains opt-in through
`KENN_DSP_NATIVE=1`, `KENN_DSP_LOUDNESS_NATIVE=1`, and
`KENN_DSP_MIX_REVIEW_DECODE_NATIVE=1`.

The existing opt-in masking kernel was also re-run at a larger 30-second,
8-stem workload: NumPy p50 `187.234 ms` versus C++ Accelerate p50
`55.405 ms` (70.4% lower), with identical findings digest. The standalone
10-second kernel receipt measured spectral p50 `1.252 ms` and masking p50
`2.033 ms` on the same Apple Silicon host.

## Real 24-bit testing-assets evidence

Two rights-unqualified internal fixtures were tested without copying or
redistributing them:

| Fixture | Format | Python p50 | Native p50 | Reduction |
| --- | --- | ---: | ---: | ---: |
| Atmosphere - Emergent - C - 78 BPM | stereo 24-bit / 48 kHz / 49.23 s | 2418.996 ms | 63.651 ms | 97.4% |
| Atmosphere - Mysteria | stereo 24-bit / 96 kHz / 25.52 s | 2479.984 ms | 25.574 ms | 99.0% |

The reference run peaked at 2,560,655,360 bytes RSS; the native run peaked at
177,291,264 bytes on the same two-file workload. Both paths completed all
reports successfully, and the native decoder reported `native_input_copied: false`.
Full machine, SHA-256, and timing receipts are stored in:

- `results/mega_optimization_audio_reference.json`
- `results/mega_optimization_audio_native.json`
- `results/mega_optimization_masking_reference.json`
- `results/mega_optimization_masking_native.json`
- `results/mega_optimization_native_kernels.json`

## Verification

- 24 Mix Review native/reference parity combinations: passed.
- 49 native Mix Review tests: passed.
- 49 native-disabled fallback tests: passed.
- Native DSP smoke and fallback smoke: passed.
- Accelerate and scalar CMake builds: passed.
- Recovered AutoMix archive CMake build and CTest smoke: passed.
- Native wheel build/install and YAML/py_compile/diff checks: passed.
- No commits were created; the existing dirty worktree was preserved.

## Decision

Keep all C++ paths opt-in. The remaining Python work in the profiled Mix
Review request is sub-millisecond to low-single-digit-millisecond orchestration
after native dispatch; a further bulk-metrics rewrite is not justified without
a complete AutoMix worker and a rights-cleared corpus. Cross-platform CI,
rights approval, and production-default promotion remain separate gates.
