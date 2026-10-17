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

(Superseded 17 Oct 2026: loudness is default-on and true peak is 8x with the
161-tap filter; see the section at the end.)

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

Accuracy, from a sine sweep in 100 Hz steps to 20 kHz, 17 phases, at 44.1, 48
and 96 kHz, edges trimmed: scipy's filter under-reads by up to 0.40 dB at 4x
and 0.13 dB at 8x, both near 20 kHz; up to 16 kHz the figures are 0.25 and
0.05 dB. 8x is a real gain but still reads a little low on the top octave.
(A first, coarser 459-tone grid missed those frequencies and reported 0.016 dB
at 4x; review caught it.) Cost: about 0.8 s more scipy time on a 4-minute
stereo mix; the native loudness call took 0.34 s on 4 minutes of 44.1 kHz
stereo noise. All timings are single runs on Jack's Mac.

The no-scipy fallback `_numpy_true_peak_dbtp` was zero-padding the time signal,
not the spectrum, so it returned the sample peak (3 dB low on a quarter-rate
sine). The first fix interpolated each chunk periodically, which review showed
reading a crest-cut loop at +1.23 dBTP against scipy's +0.20; each chunk now
carries 4096 samples of real or zero context per side and only its interior is
read, and the Nyquist bin is halved. Both have regression tests. Its ideal-sinc
interpolation still differs from scipy near Nyquist: 0.38 dB under to 0.72 dB
over across 25 white-noise draws, and about 8 dB hot on a tone gated hard at
Nyquist. Band-limited material agrees within about 0.05 dB.

Real-file promotion, one local run on Jack's Mac with a scratch runner (the
corpus is owner data and stays out of the repo, so this is recorded, not
reproducible from Git): on the owner's Audio-Assets corpus (25 files under the
150 MB cap, 24 measurable: ten full mixdowns and every sample-pack format) the
native meter matched pyloudnorm on rounded integrated LUFS, LRA and true peak
for every file. Full mix review took 8.3 s native against 38.3 s with
pyloudnorm. `KENN_DSP_LOUDNESS_NATIVE` now defaults to on; `=0`, or
`KENN_DSP_NATIVE=0`, falls back to pyloudnorm, as does a missing extension.
Extension built from this commit's source with `make native-build` (nanobind
3.1.0), SHA-256 `a99c93c9…0f66b4`. Not changed: `kenn.core.loudness_analysis` (track diagnostic) still measures
with pyloudnorm directly, now at 8x.
