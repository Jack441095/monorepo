# LAYER ALIGNMENT C++ REAL-AUDIO PARITY (V1)
### Status: parity re-qualified on smoke fixtures; real-audio re-qualification pending import

## Method

Frozen C++ spike (`cpp_spike/nla_spike.cpp`, hash recorded in the freeze
receipt) vs frozen Python reference, on identical float32 exports of
fixture pairs spanning kick/bass/synth/loop material and all perturbation
types (integer, negative, fractional, polarity, filtered, distorted).

## Results (`results/real_v1/smoke_cpp_parity.json`)

6/6 cases: xcorr AND soft-GCC offsets agree within ±0.15 samples
(most exact to 3 decimals; worst deviation 0.012 samples on the fractional
case — consistent with float32 input quantisation through parabolic
refinement).

| case | cpp_xcorr | py_xcorr | cpp_gcc | py_gcc |
|---|---|---|---|---|
| int_delay +37 | 37.000 | 37.000 | 37.000 | 37.000 |
| neg_delay −23 | −23.012 | −23.003 | −22.994 | −22.995 |
| frac 12.5 | 12.509 | 12.500 | 12.503 | 12.503 |
| polarity d14 | 14.000 | 14.000 | 14.000 | 14.000 |
| filtered d21 | 20.989 | 20.989 | 20.986 | 20.986 |
| distorted d9 | 8.985 | 8.985 | 8.980 | 8.980 |

## Real-audio corpus run (`results/real_v1/cpp_real_audio_parity.json`)

10/10 real pairs (controlled one-shots + natural stem windows): xcorr AND
soft-GCC agree within ±0.15 samples (max observed dx=0.012, dg=0.008).
No material semantic divergence.

Prior synthetic-programme parity evidence (15 vectors incl. noise-degraded,
worst case 0.143 samples on a flat LF correlation top) remains valid and
unchanged under the freeze.

Prior synthetic-programme parity evidence (15 vectors incl. noise-degraded,
worst case 0.143 samples on a flat LF correlation top) remains valid and
unchanged under the freeze.
