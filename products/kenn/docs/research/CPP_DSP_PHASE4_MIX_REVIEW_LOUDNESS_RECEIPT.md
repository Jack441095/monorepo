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

## 17 Oct 2026: 8x true peak, and the native meter becomes the default

The owner chose 8x true peak. Both the Python reference (`TRUE_PEAK_OVERSAMPLE_FACTOR`
in `local_engine.py`, `loudness_analysis.true_peak_dbtp`) and the C++ kernel now
use scipy's default `resample_poly(x, 8, 1)` filter (161-tap Kaiser, beta 5).
The C++ builds that filter at load instead of carrying a table, and matches
scipy 8x to 5e-15 dB on random and near-Nyquist test signals.

Worth knowing: the 28-of-98 tone failures behind the 4x/8x question came from
the plug-in's short 48-tap 4x FIR. scipy's 81-tap 4x filter was already close:
on 459 tones (44.1, 48 and 96 kHz, up to 20 kHz, 17 phases) its worst
under-read was 0.016 dB, against 0.0004 dB at 8x. So for this meter 8x is a
small accuracy gain. Cost: about 0.8 s more scipy time on a 4-minute stereo
mix; the native call takes 0.34 s for the whole loudness measurement.

The no-scipy fallback `_numpy_true_peak_dbtp` was zero-padding the time signal,
not the spectrum, so it returned the sample peak (3 dB low on a quarter-rate
sine). Fixed, with a regression test.

Real-file promotion: on the owner's Audio-Assets corpus (25 files under the
150 MB cap, 24 measurable: ten full mixdowns and every sample-pack format) the
native meter matched pyloudnorm on rounded integrated LUFS, LRA and true peak
for every file. Full mix review took 8.3 s native against 38.3 s with
pyloudnorm. `KENN_DSP_LOUDNESS_NATIVE` now defaults to on; `=0`, or
`KENN_DSP_NATIVE=0`, falls back to pyloudnorm, as does a missing extension.
Not changed: `kenn.core.loudness_analysis` (track diagnostic) still measures
with pyloudnorm directly, now at 8x.
