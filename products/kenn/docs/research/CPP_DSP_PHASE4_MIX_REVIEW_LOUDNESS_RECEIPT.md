# C++ DSP phase 4: Mix Review loudness candidate receipt

## Scope

The separate `packages/mix-review` engine was profiled independently from the
spectral report path. On a 10-second stereo render, calibrated loudness and
LRA were the dominant work: pyloudnorm/scipy performed repeated K-weighting
filters and overlapping gated reductions in Python-visible orchestration.

The native extension now has an opt-in `loudness_metrics` kernel that:

- applies pyloudnorm-compatible RBJ 4 dB high-shelf and 38 Hz high-pass
  stages;
- reproduces 400 ms / 75% overlap integrated-loudness gating;
- reproduces 3 s / 97% overlap LRA gating and NumPy percentile interpolation;
- uses Accelerate/vDSP biquad and convolution primitives on macOS; and
- retains a portable C++ scalar implementation for non-Accelerate builds.

The follow-up kernel pass also:

- optionally routes WAV PCM decoding through the existing native decoder for
  Mix Review uploads, avoiding the initial float64 decode allocation;
- reuses the true-peak reversal/output workspace across all polyphase passes
  and channels, avoiding per-phase allocations; and
- computes prefix sums of filtered-sample squares so the heavily overlapping
  integrated-loudness/LRA windows do not rescan the same samples repeatedly.

`local_engine._calibrated_loudness_and_true_peak` uses the loudness candidate
only when both `KENN_DSP_NATIVE=1` and `KENN_DSP_LOUDNESS_NATIVE=1` are set.
The native decoder is separately gated by
`KENN_DSP_MIX_REVIEW_DECODE_NATIVE=1`; the Python WAV decoder and
pyloudnorm/scipy implementation remain the oracle and fallback. The native
true-peak path uses the same 81-tap Kaiser FIR and zero-padded boundaries as
`scipy.signal.resample_poly(x, 4, 1)`.

## Reproduction

```text
PYTHONPATH=products/kenn/apps/backend/src:products/kenn/packages/mix-review \
KENN_DSP_NATIVE=1 \
products/kenn/apps/backend/.venv/bin/python \
products/kenn/tooling/scripts/benchmark_mix_review_native.py \
  --seconds 10 --sample-rate 48000 --repeats 20 \
  --json-out products/kenn/docs/research/phase4_mix_review_loudness_native.json
```

Current Accelerate receipt:

| Candidate | p50 complete request | Finding parity | Rounded metrics parity |
| --- | ---: | --- | --- |
| Python pyloudnorm/scipy | 81.705 ms | oracle | oracle |
| C++ K-weighting + vDSP true peak (before workspace/prefix pass) | 20.387 ms | exact | exact |
| C++ native decode + K-weighting + vDSP true peak (current) | 13.580 ms | exact | exact |

The current candidate is approximately 83.4% lower than the Python p50 and
33.4% lower than the previous native p50 on the deterministic fixture. The
fixture is stereo
PCM16, 10 seconds at 48 kHz, SHA-256
`5e6545d28a2ea8f39e6b5600bf603850cc7c848412dc27baba359307b4ae61b7`.

The result is qualified only for this opt-in synthetic/native-candidate scope;
it is not a perceptual or real-mix quality claim. Cross-platform packaging and
rights-cleared corpus validation remain promotion gates.

## Verification

- 24 seeded combinations (44.1/48/96 kHz, valid 2/3/5/10-second lengths,
  mono/stereo): rounded integrated LUFS, LRA, and true-peak parity passed.
- Native smoke/parity checks, including malformed and short-input rejection:
  passed.
- Opt-in native Mix Review decode matched the Python decoder for 16/24/32-bit
  integer and 32-bit float stereo fixtures.
- Accelerate and scalar CMake builds: passed.
- Native Mix Review plus KENN regression tests: `49 passed`.
- Native-disabled reference tests: `49 passed`.
- Native-disabled fallback smoke: passed.
- Full synthetic Mix Review qualification: 100% precision/recall/F1,
  0% false-positive rate, 4.39 ms steady-state mean, and 100% corrupted-input
  recovery with the candidate enabled.
