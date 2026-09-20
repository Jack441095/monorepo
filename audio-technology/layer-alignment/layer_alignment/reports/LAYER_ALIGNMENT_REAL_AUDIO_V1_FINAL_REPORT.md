# LAYER ALIGNMENT REAL AUDIO V1 — FINAL REPORT
### NITE DSP Intelligent Layer Alignment — Candidate Product #2
### Owner-authorised corpus: sample_pack_testing + testing_track_stems (READ-ONLY)

---

## STATUS: **PASS WITH LIMITATIONS**

**PRODUCT DECISION: AWAITING HUMAN REVIEW**
(automated gates that can be closed without ears are closed; the two
perceptual gates await the blind review pack — 52 judgements, ~1-2 s each)

## Corpus (all owner-authorised, read-only sources)

| class | target | built |
|---|---|---|
| controlled positives | ≥100 | **102** |
| healthy / no-action | ≥100 | **176** |
| natural production pairs | ≥100 | **109** |
| total | ≥300 | **387** |

Sources: 33 sample packs (evidence-verified one-shots across kick/snare/
clap/bass/perc/synth/vocal) + 8 multitrack sessions (al_james,
angeloboltini_fragments, atlantisbound, ae_mere_humsafar, stranger,
reggueton_pop, dream_of_you, amyhelmandthehandsomestrangers).
`_automix_out` excluded (another sprint's derived outputs). Rate-mismatched
pairs use derived resampled copies (flagged per case). Source files
untouched; audio never committed (`real_audio_import/` and derived fixtures
gitignored).

## Controlled real-audio accuracy (85 actionable of 102)

| metric | value |
|---|---|
| integer offset MAE | **0.127 samples** |
| fractional offset MAE | 0.000 (< reportable resolution) |
| within ±0.25 sample | **92.9%** |
| within ±1 sample | 96.5% |
| within ±2 samples | **100%** |
| polarity accuracy (when flip suggested) | **100%** |
| MAE by domain | kick 0.047 · snare 0.016 · clap 0.031 · bass 0.250 · perc 0.333 · synth 0.083 · vocal 0.219 |

17 controlled cases abstained rather than guessed: mostly `distorted`
variants (tanh drive on real one-shots degrades correlation structure — the
engine refuses instead of risking error) plus one perc int-delay. Safe,
coverage-limiting behaviour.

## Healthy real-material false-positive rate

176 healthy cases (identity copies, cross-pack decorrelated pairs,
LR4-crossover recombinations, envelope variants, tonal ambiguity pairs,
unrelated complements):

- **correction FPR: 6/176 = 3.41% → GATE PASS (≤5%), margin not large.**
  All six are ALIGN suggestions on deliberately LR4-crossover-recombined
  pairs (delays 24.5–82 samples). Mechanism: the recombine genuinely raises
  low-band summation for the suggested delay, so the benefit gate passes,
  while upper-band damage goes unpenalised — a multi-objective gating gap
  (V2-B12). No harm was inflicted on user material (suggestions are
  audition-only), and the synthetic programme had already flagged LR4 as
  delay-hostile; the real-corpus variant slipped through.

## Natural production pairs — the honest coverage finding

| action | n=109 |
|---|---|
| NO_ACTION/ABSTAIN | 107 (**98.2%**) |
| ALIGN | 2 |

Abstention taxonomy: non-overlapping-spectra guard 63 · periodic ambiguity
25 · weak relationship score 19. Root causes (forensics below): bin-level
spectral overlap under-measures sparse-harmonic musical overlap, and
10-second musical windows legitimately contain multiple near-equal lags.

Both ALIGN recommendations are exactly the predicted canonical domain:
multimic drum close-mics — kick in/out (+39.5 samples, conf 1.00, predicted
+2.46 dB low-band) and snare top/bottom with polarity flip (−112.75
samples, conf 1.00, +1.62 dB). No harmful recommendation occurred anywhere
in the run.

## Gates (frozen thresholds)

| gate | threshold | result |
|---|---|---|
| real healthy correction-FPR | ≤5% | **PASS (3.41% — all six on constructed dispersive pairs; see V2-B12)** |
| useful suggestions by ear | ≥80% | AWAITING REVIEW (pack of 52 ready) |
| harmful suggestions | ≤5% | AWAITING REVIEW (none observed mechanically) |
| uncontested <250 ms/pair | <250 ms | **NOT CERTIFIED** — host load 46–88 during window; contested p50 ≈657 ms; bench refuses uncontested claim by design |
| C++ parity on real audio | PASS | **PASS** (10/10 real pairs, xcorr+gcc agree ≤0.15 samples) |
| failure isolation | PASS | PASS (9/9 typed-safe) |

## Safety & provenance

sample_pack_testing modified: **NO** · testing_track_stems modified: **NO**
source audio committed/pushed/uploaded: **NO / NO / NO** · customer audio
used: NO · external business writes: NONE. Authorisation receipts:
`results/real_v1/../real_audio_import/LICENCE_*.json`.

## Verdict logic

The engine demonstrated: real-material estimation at sub-quarter-sample
accuracy, six unjustified corrections in 176 healthy pairs (all on constructed
dispersive material — gate hardening queued as V2-B12) and none elsewhere,
and correct domain instincts (acts on multimic drums, refuses ambiguous
loops). What blocks promotion today is (a) the two pending listening gates
and (b) actionable coverage on general natural material (1.8%) which is far
below product value even though it is the safe direction. Domain-limited
promotion (multimic/transient alignment) becomes available immediately if
the owner's blind review confirms usefulness on the ready pack.
