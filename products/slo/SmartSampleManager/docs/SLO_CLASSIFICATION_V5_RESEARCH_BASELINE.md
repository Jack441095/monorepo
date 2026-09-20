# SLO Classification — V5 Research Baseline

**Status: RESEARCH / ANALYSIS ONLY. Nothing in this document is implemented
in this phase.** Produced as part of the V4 Final Engineering Closeout,
after V4 qualification (Vocal Loop filename-evidence fix). The V4-H hybrid
heuristic+ML classifier remains FROZEN and in production; this document
answers "what would it take to move SLO from a strong hybrid classifier to
genuinely top-tier sample classification," for a future, separately
authorized V5 phase.

## 0. Method Note

Findings below are drawn from: `SmartSampleManager/tools/classification_benchmark/dataset_manifest.json`
(the 1,607-file real-vendor corpus used for V4-F/G/H qualification and this
phase's Vocal Loop fix), `SmartSampleManager/Source/AcousticClassifierWeights.h`
/ `AcousticClassifierCentroids.h` (the frozen V4-H linear head + centroids),
and the V4-F/G/H qualification reports' own published numbers (cited, not
re-derived, where noted). Where a claim is not directly measurable from
what exists in this repository, it is marked as such rather than presented
as measured fact.

## 1. Dataset

### 1.1 Class counts / imbalance (measured, `dataset_manifest.json`, n=1,607)

| Class | n | Share |
|---|---|---|
| OOD (unknown/negative) | 250 | 15.6% |
| Kick | 100 | 6.2% |
| Snare | 100 | 6.2% |
| Clap | 100 | 6.2% |
| Percussion | 100 | 6.2% |
| Vocal Phrase | 100 | 6.2% |
| Foley | 100 | 6.2% |
| FX | 100 | 6.2% |
| Riser | 100 | 6.2% |
| Bass One-Shot | 98 | 6.1% |
| Bass Loop | 90 | 5.6% |
| Hi-Hat | 85 | 5.3% |
| Music Loop | 75 | 4.7% |
| Impact | 68 | 4.2% |
| Vocal Loop | 53 | 3.3% |
| Synth Loop | 47 | 2.9% |
| Synth | 40 | 2.5% |
| Atmosphere | 1 | 0.06% |

**Imbalance ratio (largest known class : smallest known class)**: Kick/etc.
(100) : Atmosphere (1) = 100:1 — Atmosphere is effectively unevaluable (n=1
cannot support a precision/recall estimate at all; V4-H's own reports treat
it as out of scope for this reason). Excluding Atmosphere, the ratio is a
milder ~2.5:1 (Kick 100 : Synth 40), plus the already-documented thin
classes V4-H flagged as needing empirical-Bayes shrinkage (Synth n=20,
Vocal Loop n=27, Synth Loop n=24 in V4-H's *calibration-half* split, half of
the full-corpus counts above).

### 1.2 Vendor diversity (measured — significant gap)

**100% of the 1,607-file qualification corpus is a single vendor, single
pack: KSHMR, `Sounds_of_KSHMR_Vol3`.** This is the most consequential
dataset finding in this document. Every V4-F/G/H metric, and this phase's
Vocal Loop fix validation, is a within-vendor measurement. Concretely this
means:
- The BPM+musical-key filename-suffix convention this phase's fix relies on
  (§ see `SLO_VOCAL_FILENAME_EVIDENCE_REPORT.md`) is *widely used* across
  the sample-library industry (Splice, Loopmasters, Cymatics, etc.) but has
  only been verified against one vendor's specific application of it here.
  Other vendors' naming conventions may differ or be absent entirely
  (unlabeled/renamed files, no BPM/key metadata in filename at all).
- Embedding/classifier-head quality has never been measured against a
  second vendor's production/mixing style, sample-rate/bit-depth
  conventions, or sound-design aesthetic. A single vendor with a consistent
  in-house sound is a much easier classification target than the diversity
  a real user's sample library will contain (dozens of vendors, personal
  recordings, stems pulled from mixes, freeware packs of wildly varying
  quality).
- **Recommendation**: before any V5 model/data investment, acquire (or
  synthesize a labeling protocol for) a second and third vendor's
  material — even a few hundred files each — specifically to measure
  cross-vendor generalization gap. This is cheap relative to a model
  retrain and should be the first V5 action, not a late-stage validation
  step.

### 1.3 Duplicate / near-duplicate risk (not directly measured this phase)

Not evaluated in this phase (no comparison run against
`SLO_CLASSIFICATION_V4F_QUALIFICATION_REPORT.md`'s existing
`LEAKAGE_AUDIT.md`/`SAMPLE_PACK_CORPUS_AUDIT.md`, which predate this
corpus and should be re-checked rather than re-derived from scratch). A
single-pack corpus (§1.2) has an inherent structural risk: KSHMR's own
sample-design conventions (e.g. numbered variations — `KSHMR_Big_Kick_01`
through `_05`) create near-duplicate content *within* a class by
construction, which is fine for training/calibrating that class's centroid
but should not be treated as independent samples for a cross-validation
split (V4-H's stratified split, per its own report, is stratified by class
label, not de-duplicated by source-family or timbral similarity within a
class — a real leakage risk if a future V5 phase moves to a per-sample
train/eval split rather than qualifying the same frozen model repeatedly
against the same held-out corpus).

### 1.4 Train/eval leakage risk

The frozen V4-H classifier's centroids and linear head were computed once
and are static (`AcousticClassifierCentroids.h`/`AcousticClassifierWeights.h`,
compiled constants, not retrained per qualification run) — so there is no
live train/eval leakage risk *in the current architecture*, by
construction (nothing is retrained against this eval corpus). This
protection disappears the moment any future phase (V5 or otherwise)
introduces retraining against corpus data that overlaps the eval set —
worth stating explicitly as a design constraint any V5 training pipeline
must respect (hold out a vendor/pack entirely, not just a stratified
per-file split, given §1.2/§1.3).

### 1.5 Hard negatives / OOD diversity

250 OOD entries (15.6% of corpus), `label_authority: OWNER_VERIFIED`
(hand-verified, the highest-trust label tier in this manifest, vs.
`TRUSTED_PACK_LABEL` for the 1,357 known-class entries). V4-G/V4-H's own
reports already establish that OOD false-known rate is the single most
consequential unresolved metric in the whole system (41.6%/47.2% at
V4-H). This document does not re-litigate that (frozen architecture, out
of scope this phase) but notes for V5: 250 OOD examples, all presumably
drawn from the same KSHMR pack's "doesn't belong to any known bucket"
material, is likely **not diverse enough** to characterize the open-set
boundary a real, multi-vendor user library will actually present classify
against (spoken word, sound effects libraries, field recordings, other
DAWs' project stems, non-KSHMR one-shots that are subtly out-of-distribution
in ways this corpus's OOD set cannot represent).

### 1.6 Ambiguous labels / label noise

0 entries flagged `ambiguous: true` in the current manifest — either the
corpus genuinely contains no ambiguous cases (unlikely for real audio
content across 1,607 files) or the `ambiguous` field was not populated
during original labeling. Given `label_authority` is 84.4%
`TRUSTED_PACK_LABEL` (i.e., taken from the vendor's own product metadata,
not independently re-verified per file), some quantity of vendor
mislabeling should be assumed present but unquantified. V4-H's own report
already surfaces one concrete instance of this class of problem
independently (§ Vocal Loop Root Cause: `KSHMR_Whistle_*` files labeled
`Vocal Loop` ground truth — a defensible but non-obvious taxonomy choice
that a different vendor or labeler might not have made the same way).

### 1.7 Taxonomy quality

16 known classes (§1.1) plus OOD. The taxonomy conflates "musical genre of
signal processing" (Bass Loop/Synth Loop/Music Loop as three separate
loop buckets) with "sound-design category" (FX/Foley/Impact/Riser) with
"performance type" (Vocal Loop/Vocal Phrase) — a reasonable Ableton-
Browser-oriented design (see `AbletonTaxonomy.h`'s own doc comment) but
not a principled ontology, and one where subcategory boundaries are
sometimes genuinely fuzzy even to a human labeler (Impact vs FX; Music
Loop vs Synth Loop for a synth-heavy tonal loop). §3 below assesses a
hierarchical redesign.

### 1.8 One-shot vs. loop distribution

Of the 16 known classes, 6 have an explicit Loop variant (Kick, Snare,
Hi-Hat, Clap, Percussion — via `Drum Loop` tag, not a separate class in
this manifest's schema; Bass; Synth; Vocal) and the manifest's
`expected_subcategory` distribution above shows loop-labeled subcategories
(Bass Loop 90, Music Loop 75, Vocal Loop 53, Synth Loop 47 = 265 total,
16.5% of corpus) skew meaningfully smaller than their one-shot
counterparts — consistent with real sample libraries (one-shots vastly
outnumber loops in most commercial packs) but meaning loop-subcategory
recall estimates rest on smaller per-class n throughout, compounding the
thin-class calibration caution V4-H already flagged.

## 2. Current Embedding Quality — Where Do Errors Actually Come From?

Using V4-H's own published numbers (not re-derived) plus this phase's
Vocal Loop forensics, evidence attributes error sources as follows:

| Source | Evidence | Share of investigated error (qualitative) |
|---|---|---|
| Taxonomy/heuristic ambiguity (bucket G) | V4-H's Vocal Loop root cause: 88% of Vocal Loop's damage was FILENAME-evidence-hierarchy precedence, not the ML/OOD gate at all; this phase's fix directly addresses it | Dominant for Vocal Loop specifically |
| OOD calibration (global-vs-per-class threshold uniformity) | V4-G's FX/Foley/Riser recall damage (-21pp/-20pp/-21pp), fully attributed by V4-H to an inappropriately uniform global threshold and materially recovered (+3pp/+12pp/+16pp) by per-class thresholds alone, no embedding/data change | Dominant for FX/Foley/Riser |
| Embedding separation (own-class-centroid cosine similarity) | V4-H §"OOD" reports own-class-centroid cosine of ~0.83-0.87 for the damaged classes — reasonably tight, not evidence of poor embedding separation | Not implicated as a primary cause for the classes actually investigated |
| Linear-head limitation | Classifier-head numerical parity held at 3.16082e-06 max logit error across V4-F/G/H (head literally unchanged) — no evidence surfaced that the head itself, as opposed to the OOD threshold wrapped around it, is underperforming | Not directly implicated; **not independently tested** by training a stronger head to compare, so this is an absence-of-evidence finding, not a proof |
| Insufficient training data | Single-vendor corpus (§1.2), thin classes (Synth/Vocal Loop/Synth Loop, n=20-27 per V4-H's calibration half) — plausible contributor, not isolated from embedding-quality by any ablation in this repository's history | Plausible but unquantified |
| Filename heuristics | This phase's own Vocal Loop finding: real defect | Confirmed for Vocal Loop; not otherwise systematically audited across all 16 classes in this phase (out of scope — spec restricts this phase to Vocal Loop only) |
| Genuine acoustic ambiguity | Not measured this phase | Unknown — would require human-relistening audit of the residual FX/Foley/Riser/Vocal Loop errors post-V4-H, not done here (V4-H's own "Remaining Risks" section already flags this gap) |

**Overall read**: of the error sources investigated across V4-F through
this phase, none is attributable primarily to raw embedding-space
separation quality — every root cause found so far (OOD threshold
uniformity, filename-evidence precedence) sits in the *decision logic
around* the embedding, not the embedding itself. This is a genuinely
encouraging finding for a future V5 investment case (§6): the cheapest
next gains may still be decision-logic/heuristic work, not a bigger model.
But this is evidence of absence in a specific, narrow investigation
trail — not a rigorous embedding-quality audit (e.g., no t-SNE/UMAP visual
inspection of the 512-D embedding space's actual class separability, no
comparison against a stronger pretrained audio embedding backbone) has
been done in this repository's history. **That audit itself is a
recommended, comparatively cheap first V5 research step** (§6).

## 3. Hierarchical Classification (design assessment, not implemented)

A `Family -> Category -> Subcategory -> Attributes` hierarchy (e.g. Drums ->
Kick -> {Acoustic, Electronic, 808}; Vocal -> {Loop, Phrase, One-Shot} ->
{Male, Female, Processed}) would let the system express partial confidence
("this is definitely a Vocal, less certain whether Loop or Phrase") instead
of the current flat 16-way-plus-OOD decision, which is exactly the shape of
ambiguity this phase's Vocal Loop investigation surfaced. Assessment:

- **Argument for**: directly matches the shape of the errors found (Vocal
  Loop/Phrase — same Family+Category, different Subcategory; Music
  Loop/Synth Loop/Bass Loop — same Attribute (Loop), different Category).
  A hierarchical loss/confidence model could express "confidently Vocal,
  60/40 on Loop vs Phrase" honestly, which today collapses to a single
  wrong label with no visible uncertainty — this maps well onto the UX
  contract in `SLO_VOCAL_ACTIVE_LEARNING_AND_UX_DESIGN.md`'s
  AMBIGUOUS state (§ Phase L work, same closeout).
- **Argument against/complexity cost**: the current system is not a
  learned hierarchical head — it is a flat linear classifier plus a
  hand-authored taxonomy mapping (`AbletonTaxonomy::classify`). Introducing
  a genuine hierarchical *model* (not just a hierarchical *label schema*,
  which already loosely exists in `AbletonTaxonomy`'s
  category/subcategory split) requires retraining the head with a
  hierarchy-aware loss (e.g. per-level softmax, or a conditional structure
  where subcategory logits are only computed given the winning category) —
  nontrivial new ML engineering, not a heuristic change.
- **Recommendation**: do not implement a learned hierarchical head yet.
  Instead, treat `AbletonTaxonomy`'s existing Category/Subcategory split as
  a *de facto* label hierarchy already, and prioritize instrumenting it to
  expose per-level confidence (how confident in Category, separately from
  how confident in Subcategory given that Category) — this is a much
  smaller change that captures most of the UX value (§ Phase L) without a
  retrain, and would have surfaced this phase's Vocal Loop defect as a
  visibly low-confidence Subcategory decision rather than a silent wrong
  answer.

## 4. Multi-Modal Evidence Fusion (design assessment, not implemented)

Today's evidence fusion is a **hand-authored precedence chain**:
`EMBEDDED_METADATA > FILENAME > FOLDER > DSP`, with ML only permitted to
override `DSP`/`FOLDER`/empty (never `FILENAME`/`EMBEDDED_METADATA`) — this
is exactly the rule that caused the Vocal Loop defect this phase fixed
(FILENAME evidence, once present, is final, right or wrong). Modalities
available today: filename tokens, folder tokens, embedded WAV/iXML
metadata, 512-D acoustic embedding, a handful of DSP scalars (zcr,
low/high energy ratio, decay time, pitch sweep), duration, filename-parsed
BPM/key (strict), and (experimental, separate track) acoustic tempo
estimation.

- **Assessment of the current hard-precedence approach**: simple,
  fast, fully explainable (a real strength for a product that must justify
  its answers to a working audio engineer, and for `MlOverrideGate`'s
  audit trail) — but brittle exactly where evidence sources disagree
  in ways the fixed precedence order can't resolve, as demonstrated
  concretely by the Vocal Loop defect (FILENAME evidence for *category*
  was right; there was no mechanism for a different evidence source to
  contribute to the *subcategory* decision at all, until this phase).
- **Learned/calibrated fusion alternative**: a small calibrated model
  (e.g. logistic regression or a gradient-boosted tree over
  [filename-evidence-strength, DSP-scalar features, embedding-derived
  class-confidence, embedded-metadata-presence] as *features*, rather than
  a fixed override order) could in principle produce better-calibrated
  final decisions and naturally handle cases like this phase's Vocal
  Loop/Phrase disambiguation without hand-authoring a new rule per
  confusable class pair. This is a genuine V5-scale investment (needs a
  labeled dataset of "which evidence source was actually right" per
  sample, not just final ground truth) and explicitly NOT recommended
  before the single-vendor dataset gap (§1.2) is addressed — a fusion
  model trained on one vendor's evidence-reliability patterns is exactly
  the kind of overfitting this whole closeout phase was cautioned against
  disguising as progress.
- **Recommendation**: keep the hard-precedence architecture for V5's near
  term; the highest-value next step is expanding what *feeds* it (BPM+key
  filename-suffix evidence, this phase; rhythmic-structure/transient-
  profile DSP features, not currently computed at all) rather than
  replacing the fusion mechanism itself.

## 5. Open-Set Recognition Alternatives (design assessment, not implemented)

V4-G/V4-H already implemented and rejected/accepted specific points on this
spectrum; this section extends that survey for V5, using V4-H's own
candidate-method table as a starting point (global threshold, raw
per-class threshold, empirical-Bayes-shrunk per-class threshold — shipped,
class-normalized median/MAD z-score — evaluated, not shipped).

| Method | Status re: this codebase | V5 assessment |
|---|---|---|
| Global cosine threshold | V4-F baseline, superseded | Reference point only |
| Raw per-class threshold | V4-G candidate, superseded by shrinkage | Overfits thin classes per V4-H's own finding |
| Empirical-Bayes-shrunk per-class threshold | **V4-H, shipped, FROZEN** | Current production method; do not reopen (spec-mandated freeze) |
| Class-normalized (median/MAD z-score) | V4-H evaluated, not shipped (no stated advantage found) | Low priority — already tested, no gain found |
| Mahalanobis distance | Not implemented | Would require per-class covariance estimation — with the thinnest classes at n=20-27 (V4-H's calibration half), covariance estimates would be unstable; needs more data first, not a bigger open-set method |
| Energy-based OOD | Not implemented | Requires access to pre-softmax logit energy from the linear head — architecturally available (frozen head still produces logits) without retraining; a genuinely cheap experiment for V5 to run *before* any data-heavy alternative |
| Class-conditional density (e.g. a GMM per class in embedding space) | Not implemented | Same thin-class data problem as Mahalanobis |
| Conformal prediction | Not implemented | Attractive for a calibrated, statistically-principled unknown-rate guarantee — but needs a held-out calibration set per class at a scale this single-vendor, thin-class corpus doesn't yet provide (§1.2/§1.1) |
| Dedicated "unknown" class training | Not implemented (OOD is currently handled entirely via distance-to-known-centroids, never as its own learned class) | Would need the OOD population (currently 250, single-vendor) to be far larger and more diverse before this is worth the retrain cost |
| Hard-negative mining | Not implemented | Natural complement to dedicated-unknown training; same prerequisite (more diverse OOD data) |

**Recommendation ranking (cheapest-first, evidence-supported)**: (1)
energy-based OOD as a near-zero-cost experiment against the existing
frozen head (no retrain, just a different score function over already-
available logits) — try this before anything requiring new data; (2)
expand OOD corpus diversity (§1.5) before any of the data-hungry methods
(Mahalanobis, class-conditional density, conformal, dedicated-unknown
training) become worth attempting, since all of them are more data-
sensitive than the currently-shipped shrunk-threshold method, which V4-H
already chose specifically *because* of thin-class caution.

## 6. Better Model/Data Route — Ranked by Expected Value vs. Engineering Cost

Ranked using evidence gathered across V4-F/G/H and this phase, not
speculation:

1. **Multi-vendor dataset expansion** (§1.2). Highest expected value,
   lowest engineering cost (data acquisition + labeling protocol reuse —
   `LABELING_PROTOCOL.md`/`GOLDEN_SET_V1_METHODOLOGY.md` already exist and
   would not need redesigning). Every other item on this list is
   measured or trained against a single-vendor corpus today; this is the
   single biggest external-validity risk in the entire qualified system,
   and is a prerequisite for trusting any of the model-side investments
   below rather than an alternative to them.
2. **Filename/evidence heuristic audit beyond Vocal Loop** (this phase's
   method, generalized). This phase found one concrete, real, measurable
   defect using a per-sample forensic table cross-referencing ground
   truth against evidence source. The same method applied to the other
   damaged classes (FX/Foley/Riser, already OOD-threshold-attributed by
   V4-H, but not independently re-checked for a *second*, filename-
   evidence-shaped defect the way Vocal Loop had) is cheap (no retrain,
   audit + targeted rule) and has already proven high-value once.
3. **Energy-based OOD experiment** (§5) — cheap, no retrain, worth trying
   before data-heavy OOD alternatives.
4. **Per-level (Category vs Subcategory) confidence instrumentation**
   (§3's cheaper alternative to a full hierarchical retrain) — surfaces
   ambiguity for the UX contract (§ Phase L, same closeout) without new
   training.
5. **Active learning / user-correction feedback loop** (§ design doc, same
   closeout: `SLO_VOCAL_ACTIVE_LEARNING_AND_UX_DESIGN.md`). Potentially the
   highest long-run value item on this list — real usage data, real label
   diversity, real vendor diversity, all for free once users start
   correcting — but has the longest time-to-value (needs the opt-in
   pipeline built and a userbase using it before any data accumulates) and
   is explicitly design-only in this phase.
6. **Fine-tuning the existing embedding backbone** on multi-vendor data (once
   §1 is addressed). Medium cost (requires a training pipeline this
   repository does not currently have — training code is not present here,
   only inference/ONNX-export tooling per `EMBEDDING_CLASSIFIER_RESEARCH_V1.md`).
   Should follow, not precede, dataset expansion — fine-tuning against a
   single-vendor corpus risks *increasing* overfitting to that vendor's
   specific sound design.
7. **Stronger embedding backbone** (replacing the current model entirely).
   Highest cost, currently lowest-evidence item — §2 found no direct
   evidence that embedding separation itself (as opposed to decision logic
   around it) is the dominant error source for anything investigated so
   far. Worth revisiting only after §2's recommended embedding-space audit
   (t-SNE/UMAP visual inspection, per-class silhouette score) actually
   demonstrates a separation problem, not before.
8. **Metric learning / contrastive learning retrain**. Same prerequisite
   as #7 (needs evidence of an embedding-quality problem first) plus the
   same multi-vendor data prerequisite as #6 — do not start before both.
9. **Hierarchical classification head retrain** (§3's full version, beyond
   the cheap confidence-instrumentation alternative). Real engineering
   investment; ranked last not because it lacks merit but because #4
   captures most of its near-term UX value at a fraction of the cost, and
   should be tried and evaluated first.

## 7. Explicit Non-Recommendations

- Do not retrain or fine-tune anything against the current single-vendor
  corpus as the sole training source (§1.2) — any such retrain risks
  narrowing generalization further while looking like progress on this
  benchmark specifically, exactly the "benchmark overfitting disguised as
  progress" failure mode this entire closeout phase was cautioned against.
- Do not add per-class OOD threshold complexity beyond what V4-H already
  shipped without new evidence — V4-H's own candidate-method sweep already
  tested more aggressive variants and found no improvement (§5).
- Do not treat this document's rankings as a committed roadmap — it is a
  research baseline for a future, separately authorized V5 planning phase,
  per this closeout's explicit instruction not to begin V5 implementation.
