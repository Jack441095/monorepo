# LAYER ALIGNMENT FAILURE FORENSICS
### NITE DSP Intelligent Layer Alignment R&D — Candidate Product #2

Failures are catalogued honestly per §29. Every failure class below was
reproduced deterministically and either converted into an engine guard or
documented as a hard information limit.

---

## F1. Periodic ambiguity (tonal / ringing material) — HARD LIMIT

- Pure sine: xcorr MAE 27.9 samples across ±256 sweep.
- Snare-body (~170–340 Hz ringing): MAE 85.7 — correlation peaks repeat
  every ~period within the search window; multiple lags explain the data
  almost equally well.
- Multisine with few partials: same behaviour.
- GCC-PHAT does not escape this (whitening sharpens every peak equally).
- Folded phase-slope picks aliases freely when coherent bins are sparse.

**Mitigation shipped:** ambiguity ratio (global vs distinct-secondary local
maximum outside 3× mainlobe half-width) → AMBIGUOUS abstention; onset-agreement
rescue for genuine double-transients. Residual risk: material that is tonal
*and* onset-less cannot be aligned safely by any correlator-only system.

## F2. Hard PHAT on LF-dominant material — METHOD FAILURE, MITIGATED

Advanced kick (−23 samples): classic PHAT reports −5 (error +18); whitening
normalises near-empty bins to unit magnitude so noise dominates the inverse
transform. Soft γ-family converges monotonically to truth as γ→0
(γ=0.35 → −21; γ=0 → −22). Engine uses γ=0.35 for features and plain
correlation for estimates.

## F3. Per-lag normalisation bias — IMPLEMENTATION TRAP, FIXED

Energy-normalised correlation profiles shift apparent fractional peaks by up
to ~1 sample on decaying envelopes (measured 12.5-truth case reporting 13.5).
Fractional refinement now runs on the unnormalised profile. Documented as a
warning for any future production implementation.

## F4. Descending lag-axis ordering bug — CAUGHT BY SELF-TEST

Parabolic interpolation silently corrupted (+0.5-sample systematic bias)
because the negated scipy lag axis was descending while neighbour indexing
assumed ascending. Fixed; conventions now enforced by
`src/nla/selftest.py` (13 checks, all passing) run before every experiment
batch.

## F5. Energy objectives are not delay estimators — ARCHITECTURAL FINDING

On LF-dominant pairs the summation-gain objective varies <1.5 dB over a
±40-sample window (sub-period at 60 Hz exceeds typical offsets). Unregularised
search landed at +15 samples off truth; unrelated pairs yield "+5.8 dB"
false wins under unrestricted search. Fixes shipped:
estimate-then-verify architecture (correlation owns timing), bounded
verification window, constructive-low-band gate, coherence-aware abstention.

## F6. Filter boundary transients — MEASUREMENT ARTIFACT, FIXED

`sosfiltfilt` edge swings dominated shifted sums in band-limited objective
evaluation, biasing optima by ~+15 samples. Tukey tapering inside the search
removed it. Same artifact class handled in bandwise analysis.

## F7. Dispersive processing defeats single-delay correction — CONFIRMED

Delay-only recovery of ideal achievable summation:
min-phase EQ **−233%** (hurts; identity near-optimal), mic-TF −144%,
LR4 crossover −76%, allpass +73%, linear-phase EQ **+99.8%** (pure latency —
fully fixable). Bandwise offset spreads 52–194 samples against a uniform
truth of 12. Engine response: PARTIAL_SUGGESTION with band table instead of
a single number when divergence detected; improvement gate blocks harmful
delay suggestions.

## F8. Embedded plugin latency vs ground-truth bookkeeping — HARNESS BUGS, FIXED

Two harness bugs found *by the algorithms being right*: linear-phase FIR
latency (512 samples) exceeded the ±256 analysis window (estimators
"failed" because truth was mislabelled); parallel-processing cases omitted
embedded latency. After fixes, oversampled-mode recovery is 99.8% and
parallel gcc_soft MAE 0.3–0.5 samples where bulk delay truly exists.

## F9. Double transients

Two-kick composites (gap 2400): gcc_soft MAE 10.8 samples — correlation
locks onto the stronger hit mixture; gap 7200 cases fine (MAE 0.4).
Envelope-onset agreement check flags most mismatches; documented residual
risk for tightly stacked double hits.

## F10. Comb-filtered copies

+31-sample comb: benign (MAE 0.3). +77-sample comb: MAE 29.0 — the copy's
internal echo creates competing structure. Classification remains RELATED;
recommendation gated to NO ACTION unless low-band benefit clears the bar.
Residual risk accepted at feasibility stage.

## F11. Adversarial traps the engine survives

Octave-related tones abstain (coherence/prominence floor). Reversed-envelope
noise: flagged via signed-peak/polarity margin collapse rather than a false
alignment suggestion. Heavy clipping (drive 10/40): gcc_soft MAE 1.1/0.7 —
distortion barely harms soft-PHAT.

## F12. Spectral leakage inflating relationship statistics — FOUND LATE, FIXED

Without a window before the spectrum FFT, rectangular leakage (−13 dB first
sidelobe) made different-frequency tones score coherence 1.0 and PHAT
prominence >400 (octave-tone pair classified RELATED). Hann windowing fixed
the estimator but then *exposed* a second dependency: the fixed-band
coherence average ignored bands where layered drums actually interact.
Final fix: energy-weighted relationship coherence across all active bands +
Hann window + directional spectral-overlap guard. Adversarial octave tones:
4/4 abstain; all healthy families back to 100%.

## F13. Group-delay gradient fragility — DEMOTED TO COMPARATOR

Per-bin dφ/dω after windowing concentrates on short coherent runs; folded
median of the gradient biased toward 0 by null-region derivative noise
(measured 37-sample truth → ~12–14 estimate). The folded per-bin phase-
slope median supersedes it; group-delay retained in the bake-off only.

## Failure-accounting summary

| class | status |
|---|---|
| periodic ambiguity | abstention (hard limit documented) |
| hard-PHAT LF fragility | method rejected from estimate path |
| energy-objective myopia | architecture changed (estimate-then-verify) |
| dispersive single-delay harm | gating + bandwise partial output |
| harness bookkeeping | fixed; self-test extended |
| double transient / deep comb | partially mitigated; residual risk logged |
