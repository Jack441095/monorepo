# LAYER ALIGNMENT RESEARCH REVIEW
### NITE DSP Intelligent Layer Alignment R&D — Candidate Product #2

Status: research complete on synthetic ground-truth corpus (2,000+ deterministic pairs).
Isolation: `Nite_DSP_RnD/layer_alignment/` only. Production repos untouched.

---

## RQ1 — What does "alignment" actually mean mathematically?

There is no single well-defined "alignment". The programme distinguishes:

| Concept | Definition | Estimator |
|---|---|---|
| Bulk delay | b[n] ≈ g·a[n − d] | cross-correlation argmax |
| Fractional delay | d ∈ ℝ | parabolic interpolation / phase slope |
| Polarity | sign(g) | signed correlation peak |
| Static phase response | ∠Y(f) − ∠X(f) arbitrary | cross-spectrum / group delay |
| Frequency-dependent delay | τ(f) varies | bandwise offsets |
| Envelope/onset alignment | transient positions | envelope correlation |
| Energy alignment | constructive summation state | band interaction metric |

A single sample delay is exactly sufficient only for case 1–3. Cases 4–6
require different corrections per frequency region — measured extensively
(RQ5). Any product that reports one number for a dispersive pair is
measuring something that does not exist.

## RQ2 — When is time alignment beneficial?

Measured when: layers share spectral content (reinforcement/sample-replacement),
a bulk offset exists (plugin/mic/system latency), and interaction is currently
destructive. Kick-stack experiments (overlap=True): recommendations achieved
median 1.8-sample accuracy vs composite truth and improved summed low-band
energy by **+11.4 dB** and sub-band interaction by **+11.2 dB** on average.

## RQ3 — When is polarity inversion beneficial?

Polarity detection accuracy overall **89.3%** (150 cases):
identical 100%, partially related 96.7%, filtered 86.7%, distorted 83.3%,
different-envelope 80%. Key implementation finding: any correlator satisfies
corr(a,−b) = −corr(a,b); comparing separate ± runs is vacuous. The signed
peak value *is* the polarity statistic. Inverted-kick positive controls are
reliably recovered (polarity −1, delay within 2.5 samples).

## RQ4 — How does simple waveform alignment fail?

Three measured failure regimes:

1. **Periodic ambiguity** — tonal/ringing material (pure sine MAE 27.9;
   snare-body ringing ~200 Hz MAE 85.7 over ±256 search): multiple
   near-equal correlation peaks one period apart. Information-theoretic
   limit; requires abstention, not better estimators.
2. **Dispersive phase** — no single delay describes the relationship
   (RQ5).
3. **LF energy-objective flatness** — at 60 Hz a 40-sample error is <1 radian;
   energy objectives cannot own fine timing. This forced the
   estimate-then-verify architecture.

## RQ5 — Frequency-dependent phase (essential question)

Delay-only correction vs ideal complex correction (dB summation gain):

| Processing | Before | Delay-only | Ideal complex | Verdict |
|---|---|---|---|---|
| linear-phase EQ (+512-sample latency) | −1.82 | **+2.86** | +2.86 | delay fully fixes (**99.8%**) |
| allpass chain | +2.02 | +2.56 | +3.01 | partial (72.6%) |
| minimum-phase EQ | +2.94 | +2.44 | +2.98 | delay **hurts**; identity near-optimal |
| mic-like TF | +1.90 | −0.96 | +2.94 | delay **hurts** badly |
| LR4 crossover recombine | +2.50 | +0.58 | +3.01 | delay **hurts** |

Bandwise offset spread under dispersion (truth = 12 samples everywhere):
52–194 samples across bands. A global number is not just imprecise — it is
*not describing reality*. Bandwise reporting is mandatory, and NO ACTION
gating (improvement check) is what prevents harmful suggestions.

## RQ6 — Distinguishing destructive interaction from intentional layering

Yes, measurably. Kick stacks with spectrally disjoint layers (sub@48 Hz +
body@95 Hz + click — classic intentional layering): **100% NO_ACTION**
across 112 configurations including deliberately offset variants.
Spectrally overlapping (reinforcing) stacks: 83/112 recommended with real
benefit (+11 dB class). Healthy-control corpus: 230/230 correct NO_ACTION
including decorrelated stereo textures, different-pitch layers,
transient+sustain splits, wide-texture-over-mono-core, grooved offsets.

## RQ7 — Can an objective metric predict useful engineering changes?

Only as a *verifier*, never as the primary estimator. Measured:
- Energy-gain objective is nearly flat vs delay on LF material (cannot localise).
- Unrestricted search on unrelated material always finds "+5.8 dB broadband"
  false wins → must be gated by low-band benefit + coherence.
- With estimate-then-verify structure: predicted gains matched measured
  post-alignment gains in the kick-stack study (+11.2 dB sub interaction).
Multi-objective trade-off (§21) kept un-collapsed: every recommendation
reports peak-ratio, crest-delta and per-band gains separately.

## RQ8 — Can the system reliably decide NO ACTION?

Yes — this became the strongest result. See bake-off summary:
healthy false-positive rate 0/230; explicit abstention classes for
UNRELATED and AMBIGUOUS (periodic-ambiguity override with onset rescue);
adversarial octave tones abstain 100%.

## RQ9 — Low-latency feasibility

Capture/analyse architecture validated (RQ25/performance report):
full analysis suite ≈ 1–2 s per pair on this heavily-contended test
machine; core correlators are O(N log N) FFT-based and C++-portable
(numerical parity proven). Continuous real-time analysis unnecessary;
event-driven re-analysis on layer change suffices for the workflow.

## RQ10 — Differentiation

Existing tools expose waveforms/correlation meters/manual delay. The
defensible NITE DSP combination, each element backed above:
explanation-first output, bandwise interaction truth, confidence +
abstention, verified no-action intelligence, multi-layer-ready pairwise
core. Full analysis in PRODUCT_FEASIBILITY.md.

---

## Method inventory investigated (§4)

time-domain xcorr (energy-normalised), windowed Pearson, GCC-PHAT (hard),
soft-PHAT γ-family, phase-slope (folded-median), phase-slope LS (unwrap),
group-delay, magnitude-squared coherence (freq-smoothed full-length),
band-limited GCC per band, onset-envelope alignment, spectral-flux onsets,
band interaction dB, crest/peak interaction, ambiguity ratio.
All retained except naive unwrap-LS (kept as comparator only) — full
comparison in ALGORITHM_BAKEOFF.md.
