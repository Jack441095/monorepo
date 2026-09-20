# LAYER ALIGNMENT ALGORITHM BAKE-OFF
### NITE DSP Intelligent Layer Alignment R&D — Candidate Product #2

All numbers from deterministic corpus results in `results/*.json`.
Machine context: measurements taken under severe system contention
(load average 85–212); absolute times indicative only, relative ratios used.

## Offset estimation — integer delays (627 cases, offsets ±1..256, SNR ∞/20/6 dB)

| method | MAE (samples) | median AE | p95 AE | within ±2 |
|---|---|---|---|---|
| **xcorr_plain (primary)** | 10.39 | 0.00 | 97.2 | 0.939 |
| gcc_soft γ=0.35 | 5.05 | 0.00 | 3.5 | **0.943** |
| gcc_phat γ=1.0 | 11.41 | 0.02 | 64.8 | 0.820 |
| phase_slope folded-median | 36.22 | 0.47 | 255.7 | 0.581 |
| group_delay | 33.88 | 11.35 | 144.7 | 0.273 |

Per-kind story: on all 9 broadband/transient kinds xcorr_plain is essentially
exact (within-2 = 1.000, MAE ≤ 0.35). The MAE figures are dominated by the
two tonal kinds (sine 27.9, snare_body 85.7) where *any* correlator faces
periodic ambiguity — an abstention problem, not an estimation problem.
gcc_soft's p95 of 3.5 shows it degrades gracefully; hard PHAT fails outright
on advanced (-23) LF-dominant material (peak lands −5 instead of −23).

SNR robustness (gcc_soft): clean 5.37 / 20 dB 4.50 / 6 dB 5.28 MAE —
no material degradation down to 6 dB.

**Decision:** correlation owns delay. xcorr_plain primary, gcc_soft as
cross-check + prominence/confidence features.

## Fractional-delay estimation (200 cases)

| method | MAE (samples) | within 0.25 |
|---|---|---|
| **xcorr + parabolic** | **0.041** | 0.995 |
| phase_slope folded | 0.140 | 0.965 |
| gcc_soft + parabolic | 0.210 | 0.955 |
| gcc_phat hard | 0.572 | 0.894 |

Measured implementation lesson: per-lag energy normalisation reshapes the
correlation top by up to ~1 sample on decaying transients → fractional
refinement must run on the unnormalised profile.

## Polarity (150 cases)

Overall accuracy **89.3%**: identical 100%, partial 96.7%, filtered 86.7%,
distorted 83.3%, different-envelope 80%. Margin statistic exported for UI
confidence. Signed-peak statistic (see research review RQ3).

## Relationship classification / no-action quality

Healthy control corpus (230 cases, ground truth NO ACTION):

| family | n | correct no-action |
|---|---|---|
| different instruments | 120 | 100% |
| decorrelated same-spectrum | 30 | 100% |
| transient+sustain split | 16 | 100% |
| different pitch | 16 | 100% |
| wide texture + mono core | 16 | 100% |
| deliberately offset percussion | 16 | 100% |
| same source level/filtered | 16 | 100% |

**False-positive recommendation rate: 0/230 = 0.0%.**
No-action accuracy 100%. Discriminator ranking (measured separation):
energy-weighted relationship coherence > classic-PHAT prominence >
spectral-overlap fraction > soft-prominence (poor: high sidelobe floor).
Ambiguity override with onset rescue handles ringing/tonal traps; spectral
overlap guard catches harmonically-related-but-unalignable pairs (octave
tones: 4/4 abstain). Snare composites route to conservative abstention
(90/90 AMBIGUOUS post windowing fix — body ringing is genuinely ambiguous;
band evidence is reported but no delay is suggested).

## Robustness under processing (parallel-processing detection, truth incl.
embedded plugin latency)

| mode | xcorr MAE | gcc_soft MAE |
|---|---|---|
| parallel compression (+latency) | 27.4 | **0.30** |
| saturation (+latency) | 29.6 | **0.50** |
| band-filtered copy | 123.1 | 40.7 |
| multiband split/combine | 108.2 | 109.7 |
| oversampled (linear-phase, 128-lat) | 132.7 | 127.8 |

Interpretation: with a true bulk delay, gcc_soft is sample-exact. The large
"MAE" rows are dispersive/no-bulk-delay cases where a single-number ground
truth does not exist — precisely the bandwise-reporting regime (research
review RQ5), not estimator failures.

## Sample-rate matrix (36 cases; ms-domain errors)

44.1/48/88.2 kHz: MAE ≈ 0.000 ms across methods. 96 kHz ≈ 0.06 ms
(sub-half-sample regime). Sample-delay↔time conversion verified correct at
all four rates.

## Transient alignment comparison (90 cases)

xcorr 0.04 MAE vs envelope-onset 11.2 (hop quantisation) vs first-flux-onset
75.8 (detector too coarse as-is). Correlation wins even on transient
material when peaks are unambiguous; onsets retained as ambiguity-rescue
side-information and for future transient-centric UI.

## Search / verification architecture

Final engine: estimate (correlation, ambiguity-gated) → verify (bounded
±10-sample interaction search around estimate, both polarities,
quarter-sample refinement) → gate (improvement ≥ threshold AND constructive
low-band gain ≥ 2.5 dB in active bands) → explain. Positive-control battery:
9/9 exact-or-near estimates including inverted-polarity recovery;
aligned pair → NO_ACTION; disjoint-layer stack → NO_ACTION.

## C++ spike parity

Independent clang++ -O2 implementation (own FFT, energy-normalised xcorr,
soft-PHAT): agreement with Python reference within float32 input
quantisation — worst case 0.143 samples on the kick's flat LF correlation
top, ≤0.02 samples elsewhere; exact (<1e-3) on sharp-peak materials.
Parity harness: `experiments/run_cpp_parity.py` → `results/cpp_parity.json`.
