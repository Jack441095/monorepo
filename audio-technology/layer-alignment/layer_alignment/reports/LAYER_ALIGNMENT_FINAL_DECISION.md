# LAYER ALIGNMENT FINAL DECISION
### NITE DSP Intelligent Layer Alignment R&D — Candidate Product #2

---

## PROGRAMME
NITE DSP Intelligent Layer Alignment R&D

## VERDICT: **CONTINUE R&D** (promote to licensed-audio validation stage;
product prototype gate defined below — not yet PRODUCT PROTOTYPE)

Rationale in one paragraph: the two-layer core survived every falsification
attempt on synthetic ground truth — estimation is sample-accurate where
information exists, abstention is reliable where it does not, no-action
intelligence is perfect on 230 healthy controls, and measured benefit on
reinforcing layers is large (+11 dB class). The single remaining unknown is
transfer from deterministic synthetic material to real production audio,
which cannot be closed without licensed owner/customer material (explicitly
out of bounds for this programme). Everything else is engineering.

## EXPERIMENTS
13 experiment families + C++ parity spike + adversarial suite; conventions
enforced by a 12-check numerical self-test run before every batch.

## SYNTHETIC PAIRS
≈2,040 analysed pairs (>14,000 individual estimates); all deterministic,
seeds documented; manifests committed.

## METHODS COMPARED
xcorr_plain, windowed Pearson, GCC-PHAT (hard), soft-PHAT γ-family,
folded phase-slope, unwrap-LS slope (comparator), group-delay gradient
(comparator), freq-smoothed coherence, band-limited GCC ×6 bands,
onset-envelope alignment, spectral-flux onsets, band interaction dB,
crest/peak interaction, ambiguity ratio, directional spectral overlap,
energy-weighted relationship coherence.

## BEST OFFSET METHOD
Time-domain energy-normalised cross-correlation (primary estimate) +
parabolic refinement on the unnormalised profile; gcc_soft γ=0.35 as
cross-check/confidence feature. Architecture: estimate-then-verify.

## OFFSET ERROR
Broadband/transient kinds: within ±2 samples = 94–100% by kind
(MAE ≤ 0.35 per kind); overall MAE dominated by tonal ambiguity classes
(sine/snare-body) which are abstention cases, not estimation failures.

## FRACTIONAL OFFSET ERROR
0.041 samples MAE (parabolic), 0.995 within ±0.25 samples.

## POLARITY ACCURACY
89.3% overall (identical 100% / partial 96.7% / filtered 86.7% /
distorted 83.3% / different-envelope 80%).

## HEALTHY FALSE-POSITIVE RATE
0/230 = **0.0%** (final engine; includes deliberately-offset percussion,
decorrelated textures, level/filtered same-source pairs).

## NO-ACTION ACCURACY
100% healthy corpus; intentional-layering stacks 112/112 NO_ACTION;
octave-tone traps 4/4 abstain; snare composites 90/90 conservative
abstention.

## FILTERED-SIGNAL ROBUSTNESS
Polarity 86.7% under min-phase EQ; offset estimation unaffected by
filtering of copy content (MAE ≤0.05 on bandnoise); dispersive processing
correctly routed to bandwise/partial output instead of single delay
(delay-only recovery: linear-phase 99.8%, allpass 73%, min-phase/mic-TF/LR4
negative → gated to NO ACTION).

## DISTORTED-SIGNAL ROBUSTNESS
Heavy clipping (tanh drive 10/40): offset MAE 1.1/0.7 samples.
Distorted bass copies: exact recovery (-17.0 truth → -17.0 suggested).
Polarity under distortion 83.3%.

## REAL-TIME FEASIBILITY
Capture/analyse architecture chosen; full suite is ~20 FFT-class ops per
analysis event; continuous real-time rejected as unnecessary. Absolute
timings captured under severe machine contention (load 85–212) and are
non-representative; uncontested bench required at alpha.

## C++ PARITY
PASS — independent clang++ implementation agrees with Python reference
within float32 input quantisation (worst 0.143 samples on flat LF peak,
≤0.02 typical, <1e-3 sharp-peak). `results/cpp_parity.json`.

## BIGGEST TECHNICAL STRENGTH
Calibrated refusal: the system reliably distinguishes fixable interaction
from intentional layering and from unalignable material — the property no
surveyed tool category has, and the one producers actually need.

## BIGGEST TECHNICAL WEAKNESS
Tonal/ringing layers without transient side-information remain
information-limited (periodic ambiguity): correct behaviour is abstention,
but perceived value on such material is low. Synthetic→real transfer is
the corresponding evidence gap.

## PRODUCT DIFFERENTIATION
Explanation-first structured output; bandwise interaction truth (single
global delay measurably wrong or harmful under dispersion); explicit
confidence + abstention; verified NO ACTION as first-class outcome;
benefit quantification (+dB predictions validated against measurement)
before the user commits an ear; pairwise core ready for N-layer extension.

## PRODUCTION REPOS MODIFIED
NONE

## OWNER AUDIO USED
NO

## CUSTOMER AUDIO USED
NO

## AI ATTRIBUTION IN COMMITS
NONE

## NEXT STEP
Licensed-material validation sprint (CONTINUE R&D stage):
1. Acquire written permission for a small set of owner multitrack stems
   (kick/bass/snare layers, parallel chains) — READ-ONLY import into an
   isolated dataset area, never mutating source projects.
2. Re-run the frozen engine unchanged; report healthy-FPR, suggestion
   precision, and producer-judged usefulness on real material.
3. Gate to PRODUCT PROTOTYPE: healthy FPR ≤5% on real unrelated pairs,
   ≥80% of suggestions judged useful by ear, uncontested performance bench
   meeting capture/analyse budget (<250 ms/pair typical session sizes).
4. If the gate fails on transfer (not on tuning), PARK with full write-up —
   the pairwise interaction analyser remains reusable as telemetry/
   educational feature surface.
