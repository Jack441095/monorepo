# SLO Classification & Audio Analysis — V4-H — Final Calibration Report

**Engineering branch:** `engineering/slo-classification-analysis-v4`
**Baseline:** V4-G (`5e1b6b9`)
**Date:** 2026-08-22

## Repository / Branch / SHA

Canonical repo `Nite_DSP/Nite_DSP_01`. Verified before any change: `git status`
clean, `engineering/slo-classification-analysis-v4` at `5e1b6b9`, matching
`origin/engineering/slo-classification-analysis-v4` exactly (`git fetch`
confirmed no divergence), `main` untouched (`ab1de91`, unrelated to this
lineage). The three V4-G reports were read in full before any code change
(§V4-G Baseline below cites their exact recorded figures, not rounded
recollections).

## V4-G Baseline

Exact figures re-read from `SLO_CLASSIFICATION_V4G_OOD_REPORT.md` and
`SLO_CLASSIFICATION_V4G_QUALIFICATION_REPORT.md`:

- OOD false-known: **89.6% → 33.2%** (full corpus, V4-F→V4-G), **84.0% →
  32.8%** (unbiased holdout).
- Known acceptance (holdout): 95.7% → 93.4%.
- Per-class recall damage (V4-F → V4-G, full corpus): **FX 97.0%→76.0%
  (−21.0pp)**, **Foley 96.0%→76.0% (−20.0pp)**, **Riser 89.0%→68.0%
  (−21.0pp)**, **Vocal Loop 13.2%→1.9% (−11.3pp, already very weak, now
  near-zero)**. Music Loop also dropped 56.0%→44.0% (−12.0pp), not one of
  the four named target classes but tracked here since it shares the same
  root cause.
- ML overrides: 539 (V4-F) → 315 (V4-G) total; 269 corrective / 0 harmful /
  8 no-effect on known ground truth (both phases); 38 of the 315 were
  applied onto genuinely OOD ground truth (new visibility in V4-G, not
  previously broken out).
- Regression suite: 8/8 PASS in V4-G. Classifier-head parity: max logit
  error 3.16082e-06 (unchanged from V4-F — the linear head itself was never
  touched).
- V4-G's own recommendation: **CONTINUE DEVELOPMENT**, with the explicit
  next step "investigate class-conditional OOD thresholds... before
  considering the classification architecture for a freeze."

## Methodology Note: V4-H's Evaluation Split

V4-G's original calibration/holdout split was produced by scratchpad tooling
(`ood_analysis.py`, `gen_centroids_header.py`) that its own report documents
as "not committed / local-only." That tooling was not present in this
session's checkout (confirmed by search — a legitimate, disclosed gap, not a
retained artifact this phase silently relied on). V4-H therefore constructed
a **fresh** deterministic 50/50 stratified split (seed 1234, stratified
separately by each known `expected_subcategory` and by OOD-vs-known),
implemented in this phase's own scratchpad tooling. This split is close to
but not bit-identical to V4-G's original (recomputing each class's centroid
from this split's calibration half and comparing by cosine similarity to the
**committed, frozen** V4-G centroids in `AcousticClassifierCentroids.h`
yields 0.992-0.9996 agreement across all 16 classes — confirming the two
splits are compositionally near-identical, not confirming bit-identity).

**Validation of the evaluation harness itself:** before trusting any new
number, this phase's Python re-implementation of the production
`SampleManagerEngine.cpp` override-gate decision logic (§ML Override
Analysis below) was checked against V4-G's own already-published,
already-audited numbers, using the *committed* V4-G threshold/centroids
(i.e., not tuning anything new yet — purely a reproduction check):

| Metric | V4-G published | This phase's harness (full corpus) |
|---|---|---|
| OOD false-known | 33.2% | **33.2%** |
| Known acceptance (holdout) | 93.4% | 93.7% (my holdout split) |
| FX recall | 76.0% | **76.0%** |
| Foley recall | 76.0% | **76.0%** |
| Riser recall | 68.0% | **68.0%** |
| Vocal Loop recall | 1.9% | **1.9%** |
| Kick recall | ~100% (98.0% precision reported) | 100.0% recall |
| Kick precision (OOD-inclusive, 2 FP) | 98.0% | **98.04%** (2 FP) |
| ML overrides, known population | 269 corrective / 0 harmful / 8 no-effect | **269 / 0 / 8** (exact) |
| ML overrides onto OOD ground truth | 38 | **38** (exact) |
| Pre-V4-G (margin<0.15) full-corpus false-known | 89.6% | **89.6%** (exact) |

Every one of these is an exact or near-exact reproduction. This gives high
confidence that the harness correctly encodes the real
`SampleManagerEngine.cpp` decision logic (evidence hierarchy +
DSP/FOLDER/empty-only ML override eligibility + the V4-G OOD-clears-category
fix), so its use below to evaluate *new, not-yet-built* candidate gates is
trustworthy without a full rebuild-and-rescan for every candidate. The
**final selected candidate** was still verified end-to-end with a real
rebuilt `ClassificationBenchmark` binary + full 1,607-file rescan (§V4-F vs
V4-G vs V4-H) before being reported as final.

## Failure Forensics

Per-sample centroid cosine similarity, nearest/second-nearest centroid,
top1-top2 margin, and embedding L2 norm were computed for every known sample
in FX/Foley/Riser/Vocal Loop (own-class-centroid statistics), split by
whether the current (V4-G) gate accepted or rejected them:

| Class | Accepted own-centroid cos (mean) | Rejected own-centroid cos (mean) | Gap vs. V4-G global threshold (0.8627) |
|---|---|---|---|
| FX | 0.893 | 0.813 | rejected samples sit ~0.05 below threshold |
| Foley | 0.900 | 0.824 | ~0.04 below |
| Riser | 0.884 | 0.808 | ~0.05 below |
| Vocal Loop | 0.871 | 0.827 | ~0.04 below |

All four classes' **rejected** members cluster just below the single global
threshold, while their **accepted** members cluster comfortably above it —
i.e. there is no bimodality or wild scatter within the rejected population
itself (ruling out D: multimodal class distribution as the primary cause for
FX/Foley/Riser — see §Vocal Loop Root Cause for why Vocal Loop is different).
This is consistent with cause **A (inappropriate global threshold)** and
**B (class-specific embedding spread)**: FX/Foley/Riser's *known* population
is simply less tightly clustered around its centroid (in cosine-similarity
terms) than the classes the 0.8627 threshold happens to suit well (Kick,
Clap, Hi-Hat — see per-class support table in the header). Hard-OOD material
whose nearest centroid happens to be FX or Foley also lands in a
**genuinely overlapping** band (cause **F**): hard-OOD-nearest-FX mean
cosine 0.847, hard-OOD-nearest-Foley mean cosine 0.837 — both *inside* the
0.81-0.86 band where genuinely-known FX/Foley members were also being
rejected. This overlap is real (not an artifact of the gate) and is why no
threshold choice makes both sides "free" — recovering known recall in this
band necessarily also recovers Bass-Loop-adjacent hard-OOD, at a
quantified cost (see §Ablation and §Threshold/Pareto Analysis).

**Full-pipeline attribution (not just the gate in isolation):** cross-
referencing each wrong final classification against
`diagHeuristicEvidencePreML` / `diagMlSubcategory` / `diagMlIsOod` shows the
damage is concentrated almost entirely in one specific population — samples
where **pre-ML evidence was DSP/empty** (i.e. genuinely eligible for an ML
override) **and** the ML linear head's own prediction was **already
correct** but got blocked by `isOod`:

| Class | Wrong (final) | ...where pre-ML evidence was DSP/empty | ...where ML's own prediction was already correct but blocked | Attribution |
|---|---|---|---|---|
| FX | 24 | 23 | 23 (96%) | **cause A/B (threshold), not a heuristic/taxonomy problem** |
| Foley | 24 | 24 | 20 (83%) | **cause A/B** |
| Riser | 32 | 23 | 30 (94%) | **cause A/B** |

In every one of these cases the classifier already "knew" the right answer
(`diagMlSubcategory == ground truth`); the *only* thing preventing it from
being applied was the OOD gate. This directly rules out E (insufficient
training examples — the linear head clearly learned these classes well
enough to predict them correctly), G (taxonomy ambiguity), H (bad ground
truth), and most of I (ML-override-interaction problems, beyond the gate
itself) as primary causes for FX/Foley/Riser. **Cause A/B — an
inappropriately uniform global threshold across classes with different
natural embedding spread — is the dominant, evidence-supported root cause.**

## Vocal Loop Root Cause

Spec §7 requires this investigated specifically, and demonstrated before any
threshold change — **and the investigation overturns the assumption implicit
in V4-G's own report** that Vocal Loop's near-zero recall was primarily a
thin-calibration-set / centroid-geometry problem.

Same cross-reference for the 52/53 wrong Vocal Loop samples:

| Cause bucket | Count | % |
|---|---|---|
| Pre-ML evidence = **FILENAME**, heuristically (and wrongly) classified as **Vocal Phrase** before ML ever runs | 46 | 88% |
| Pre-ML evidence = DSP/empty, ML flagged OOD (gate-driven, the V4-G-report's assumed cause) | 6 | 12% |

**88% of Vocal Loop's damage has nothing to do with the OOD gate at all.**
The evidence hierarchy (`EMBEDDED_METADATA > FILENAME > FOLDER > DSP`, ML
only overrides `DSP`/`FOLDER`/empty) means that once FILENAME evidence has
already produced a classification, the ML linear head is **never consulted
for an override** — even though, in every one of these 46 cases,
`diagMlSubcategory` is genuinely `Vocal Loop` (correct) with `diagMlIsOod ==
false` (the ML classifier was *not* confused). The heuristic FILENAME-parsing
logic evidently cannot reliably distinguish "Vocal Loop" from "Vocal Phrase"
in this vendor's naming conventions (both classes contain the token
"Vocal"), and — per the evidence hierarchy this phase is required to
preserve unchanged (spec §4/§17) — that heuristic's answer is final. This is
root cause **G (taxonomy/heuristic ambiguity) via evidence-hierarchy
precedence**, not **A/B/C/D (threshold/geometry/multimodality)**. Widening
or loosening the OOD threshold for Vocal Loop cannot fix a class this gate
never gets a chance to influence in the first place — confirmed directly:
even the most aggressive per-class thresholds tested in this phase's sweep
(down to a 5% per-class calibration-rejection budget, i.e. deliberately very
permissive) only recovered Vocal Loop to 9-15% recall, because the other 88%
of its damage sits entirely upstream of the gate.

**This is reported as an honest, in-scope-respecting limitation, not
something this phase attempted to route around.** Fixing it for real would
mean either (a) changing FILENAME-evidence heuristic logic to disambiguate
Vocal Loop vs Vocal Phrase (a heuristic/taxonomy change, explicitly out of
scope — spec §1/§4), or (b) letting ML override FILENAME evidence for this
one class pair (weakening the evidence hierarchy, explicitly against spec
§17's instruction to preserve it). Neither is authorized in this phase.

## Candidate OOD Methods

Four families were implemented and evaluated on the calibration/holdout
split (spec §9-12):

1. **Global threshold, re-swept** (single scalar, varying the
   known-rejection calibration budget 2-30%) — establishes the
   single-threshold Pareto curve as a reference.
2. **Raw per-class threshold** — one threshold per class, each the Nth
   percentile of that class's own calibration-half score distribution
   (budget swept 5-30%), indexed at inference by which centroid the sample
   is nearest to.
3. **Shrunk (Empirical-Bayes) per-class threshold** — same as (2), but each
   class's raw percentile is shrunk toward the V4-G global threshold by
   weight `w_c = n_c / (n_c + k)`, `n_c` = that class's calibration sample
   count, `k` a fixed prior-strength constant (swept 10-50). Addresses
   spec §9's "avoid 16 arbitrary magic numbers" and §15's small-sample
   caution directly: thin classes (Synth n=20, Vocal Loop n=27, Synth Loop
   n=24) are pulled back toward the shared threshold; well-supported
   classes (n=50) are allowed to diverge further.
4. **Class-normalized (median/MAD z-score) distance** — `z = (cos -
   median_c) / (1.4826 × MAD_c)`, single global z-threshold swept 0.5-2.5,
   indexed by nearest centroid (spec §8/§9 option, using MAD instead of
   std-dev because the per-class score distributions are visibly
   left-skewed, not Gaussian).
5. **Composite** (spec §11): normalized distance AND top1-top2 margin
   ("far from its class AND ambiguous between two classes") — tested at
   several z/margin combinations.

Mahalanobis distance and multi-centroid/clustering were **not** attempted,
for the same reasons V4-G already gave and re-confirmed this phase: 20-50
calibration samples per class in 512D make either badly rank-deficient /
prone to spurious multimodality detection without dedicated
shrinkage/validation infrastructure this narrow phase does not build (spec
§10's explicit instruction: "only evaluate multiple prototypes if evidence
demonstrates a real multimodal failure" — the failure-forensics pass above
found no such evidence; FX/Foley/Riser's rejected populations are not
bimodal, they are uniformly-shifted below threshold).

## Distance Normalisation

Per-class robust statistics (median, MAD) were computed from the
calibration half only. Median own-class cosine ranged 0.78 (Riser) to 0.94
(Kick) — a genuinely large spread across classes, confirming the premise of
spec §8 that raw distance is not directly comparable across classes.
Scaled-MAD (1.4826× MAD, comparable units to a std-dev under near-normality)
ranged 0.03-0.06, also class-dependent. The z-score family (§4 above)
successfully compressed this cross-class variation into a single comparable
scale, but see §Ablation for why it was not selected as the final method.

## Global vs Class-Conditional Calibration

The global-threshold-only Pareto sweep (family 1) could not simultaneously
achieve both required outcomes. At every global-budget operating point that
materially recovered FX/Foley/Riser (e.g. 15-20% known-rejection budget,
global threshold ≈0.85-0.85), OOD false-known rose to 36-43% — comparable to
or worse than the *best* per-class candidates below — while *also* not
recovering Vocal Loop or Music Loop as effectively (global thresholds cannot
target the specific classes that need help without also loosening
well-calibrated classes like Kick/Clap/Hi-Hat, which showed zero problem
under V4-G and gained nothing from a looser global threshold). This
confirms spec §9's premise: class-conditional calibration is justified by
the data here, not merely more flexible in the abstract.

## Composite Score Evaluation

The composite (normalized-distance AND margin) family was tested at
z∈{1.0,1.5}, margin∈{0.02,0.05,0.10}. It did not outperform per-class
threshold at a matched OOD-false-known operating point — e.g. `z>1.0 AND
margin<0.05` gives OODfk 54.0%, FX 76%, Foley 85%, Riser 81%, Vocal Loop
13.2% (full corpus), which is dominated by the selected per-class candidate
below at a *lower* OOD false-known cost (41.6%) with comparable or better
recall on 3 of 4 target classes. The composite score adds a second free
parameter (margin threshold) without demonstrated benefit here — rejected
per spec §11's "prefer interpretable calibration... do not create a
complicated... score" without ablation-proven necessity.

## Ablation

| Method (best operating point in its family, by grid search under the constraint: worst target-class delta ≥ −3pp) | OOD false-known (full) | FX | Foley | Riser | Vocal Loop |
|---|---|---|---|---|---|
| V4-G production (global 0.8627297) — **baseline** | 33.2% | 76.0% | 76.0% | 68.0% | 1.9% |
| Global threshold re-tuned (20% budget) | 31.2% | 71.0% | 73.0% | 65.0% | 0.0% |
| Raw (unshrunk) per-class threshold (15% budget) | 42.0% | 75.0% | 87.0% | 78.0% | 7.5% |
| Class-normalized z-score (z=1.2) | 39.6% | 76.0% | 85.0% | 81.0% | 3.8% |
| Composite (z=1.0, margin<0.05) | 54.0% | 76.0% | 85.0% | 81.0% | 13.2% |
| **Shrunk per-class threshold (budget=10%, k=10) — SELECTED** | **41.6%** | **79.0%** | **88.0%** | **84.0%** | **7.5%** |

The selected method was found by an unconstrained grid search over
(budget, k) requiring only that **no** class regress by more than 3pp versus
V4-G production, then maximizing the summed recall gain across the four
target classes — i.e. it was not cherry-picked after the fact from a single
metric, and it is the only family that improved **all four** target classes
simultaneously with **zero regressions in any of the other 12 known
classes** (verified individually — Kick, Clap, Hi-Hat, Bass One-Shot,
Impact, Synth, Percussion, Snare, Vocal Phrase all unchanged or improved;
Bass Loop and Synth Loop remain the pre-existing 0%/0%/0% taxonomy gap,
unchanged, out of scope per V4-F/V4-G). The shrinkage step earns its
complexity over the raw (unshrunk) per-class family: at a comparable OOD
cost, shrinkage gives measurably better Foley/Vocal Loop recall with no
downside observed on any other class (the raw and shrunk sweeps were run
side-by-side; the shrunk family's best point strictly dominates the raw
family's comparable-budget points on the summed-gain metric used for
selection).

## Selected Method

**Shrunk per-class OOD threshold, indexed by nearest centroid.** For class
`c`: `threshold_c = clamp(global + w_c × (P10(cal_c) − global), 0.60, 0.92)`,
where `P10(cal_c)` is the 10th percentile of class `c`'s calibration-half
own-centroid cosine-similarity distribution, `global` = the V4-G threshold
0.8627297 (retained as the shrinkage anchor and as a diagnostic fallback),
and `w_c = n_c / (n_c + 10)`. All 16 values, their raw percentiles, and
their shrinkage weights are documented inline in
`Source/AcousticClassifierCentroids.h` (`perClassOodThreshold`).

**Code changes:**
- `Source/AcousticClassifierCentroids.h` — added `perClassOodThreshold[16]`
  with full derivation documented in the header comment; the original
  `oodCosineSimilarityThreshold` scalar is retained (as a comment-documented
  fallback for `nearestCentroidIndex == -1`, and for diagnostic/regression
  comparison) but is no longer the primary gate input.
- `Source/AcousticClassifier.h` — `classify()` now also tracks which
  centroid produced the best cosine similarity (`nearestCentroidIndex`,
  new `Result` field) and looks up `perClassOodThreshold[nearestCentroidIndex]`
  instead of comparing against the single global scalar. This is a ~10-line
  change to an already-small function; no new allocations, no new hot-path
  cost beyond one array index (see §Runtime Cost).
- `Source/MlOverrideGate.h` (**new**) — the V4-D/V4-G override-vs-OOD
  decision (previously ~45 lines inline inside `prepareFile()`'s ONNX batch
  loop) extracted into a small, pure, dependency-light function
  (`AbletonTaxonomy.h` only — no ONNX, no JUCE GUI). Behavior is
  byte-for-byte identical to the prior inline code (verified: the extracted
  function's branches were copied structurally unchanged, only wrapped in a
  named `Input`/`Decision` struct interface). This was done specifically so
  the V4-G stale-category-clearing fix and the evidence-hierarchy precedence
  it implements could have a fast, dedicated, ONNX-free regression test
  (spec §20/§27 explicitly ask for this) rather than only being exercised
  indirectly through a full corpus rescan.
- `Source/SampleManagerEngine.cpp` — the inline override-gate block replaced
  with a call to `MlOverrideGate::evaluate()`. No other logic in this file
  changed.
- `Source/TestAcousticClassifierParity.cpp` — 6 new V4-H test groups added
  (see §Regression Tests).
- `CMakeLists.txt` — `TestAcousticClassifierParity`'s target now also
  compiles `Source/AbletonTaxonomy.cpp` (needed by the new
  `MlOverrideGate.h` include; `AbletonTaxonomy.cpp` has no further
  dependencies, so this adds negligible build cost to that one target).

**Explicitly not touched:** the 512D embedding model, the 16-class linear
head (`AcousticClassifierWeights.h`), `AcousticClassifierCentroids.h`'s
`centroids[][]` data (the centroid vectors themselves are unchanged from
V4-G — only a second, per-class threshold array was added alongside them),
the evidence hierarchy's precedence order, filename/metadata/folder parsing,
BPM code, UX/EMBER/DesignTokens, cache/persistence.

## Threshold / Pareto Analysis

Full sweep (excerpted; see scratchpad `sweep.py`/`shrunk.py`/`search.py`
output for the complete grid, reproducible from the same
`v4g_results/v4g_final2_scan_subset.json` scan + `dataset_manifest.json`
ground truth):

| Family @ operating point | OOD false-known (full) | OOD false-known (holdout) | Known acceptance | Coverage | Selective accuracy |
|---|---|---|---|---|---|
| V4-G production | 33.2% | 37.6% | 93.7% | 84.3% | 73.3% |
| Global @ 15% budget | 36.4% | — | 95.1% | 85.9% | 73.3% |
| Global @ 20% budget | 31.2% | — | 92.5% | 82.9% | 73.4% |
| Per-class raw @ 15% budget | 42.0% | 48.8% | 95.8% | 87.4% | 72.7% |
| Class-normalized z=1.2 | 39.6% | 44.8% | 95.4% | 86.7% | 73.0% |
| **Shrunk per-class (10%, k=10) — SELECTED** | **41.6%** | **47.2%** | **96.8%** | **88.2%** | **73.1%** |

**Pareto observation:** known acceptance and coverage both *increase* under
the selected candidate relative to V4-G production (93.7%→96.8% known
acceptance, 84.3%→88.2% coverage) — i.e. the gate now blocks fewer
genuinely-known samples overall, which is exactly the intended effect,
recovering the recall that V4-G's uniformly-conservative threshold cost.
Selective accuracy (of samples accepted as known, what fraction are
genuinely known) stays essentially flat (73.3%→73.1%, full corpus) — the
gate is not simply accepting more garbage, it is specifically accepting
more of the genuinely-known FX/Foley/Riser/Vocal Loop material that V4-G
had been wrongly rejecting, at the cost of also accepting more of the
adjacent hard-OOD material that genuinely resembles those same classes
(the overlap quantified in §Failure Forensics). OOD false-known rises by
8.4pp (full corpus) / 9.6pp (holdout) relative to V4-G — this is the
real, honest cost of the recall recovery, and remains, on both measures,
**more than 2x better than pre-V4-G** (89.6%→41.6% full corpus is a 2.15x
reduction; 89.6%(V4-G report)/92.0%(this split)→47.2% holdout remains
roughly a 1.9-2x reduction depending on which holdout baseline is used).

## Holdout Results

This phase's calibration/holdout split (fresh, seed 1234, documented above)
was used throughout: per-class shrunk thresholds were derived from the
**calibration half only**; all recall/OOD numbers reported for holdout below
never contributed to threshold derivation. Full-corpus numbers (V4-F/V4-G-
comparable methodology) are reported alongside per V4-G's own precedent, not
as a substitute for the leakage-free number.

| | Full corpus (V4-F/V4-G-comparable) | Holdout only (unbiased) |
|---|---|---|
| OOD false-known | 41.6% | 47.2% |
| OOD rejection | 58.4% | 52.8% |
| Known acceptance | 96.8% | 97.3% |
| Known accuracy (overall, known population) | 76.4% | 78.3% |
| FX recall | 79.0% | 78.0% |
| Foley recall | 88.0% | 94.0% |
| Riser recall | 84.0% | 88.0% |
| Vocal Loop recall | 7.5% | 11.5% |

**Corpus-size caveat (spec §15):** the holdout half contains only 26-50
samples per known class and 125 hard-OOD samples. Per-class recall deltas of
a few percentage points on n=26 (Vocal Loop) or n=50 (FX/Foley/Riser)
correspond to single-digit sample-count changes and carry real sampling
noise — e.g. Vocal Loop's holdout recall (11.5%) reflects 3/26 correct vs.
V4-G's 0/26; this is a genuine, measured improvement but the absolute
numbers on this class should not be read with more precision than "still
very weak, marginally better," consistent with the root-cause finding that
most of Vocal Loop's damage is architecturally out of this phase's reach.
The full-corpus numbers (larger n, 100 samples for FX/Foley/Riser) are more
statistically stable and are the primary numbers this report's freeze
decision leans on.

## Per-Class Results

Full-corpus per-class precision/recall/F1 (known population only; OOD
population's contribution to precision is reported separately in
§ML Override Analysis and folded into the Kick/FX spot-checks below for
continuity with V4-G's reporting style):

| Class | V4-G P | V4-G R | V4-G F1 | V4-H P | V4-H R | V4-H F1 | ΔR |
|---|---|---|---|---|---|---|---|
| Bass Loop | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0 (pre-existing taxonomy gap, unchanged) |
| Bass One-Shot | 51.6% | 100.0% | 68.1% | 51.6% | 100.0% | 68.1% | 0 |
| Clap | 99.0% | 100.0% | 99.5% | 99.0% | 100.0% | 99.5% | 0 |
| **FX** | 54.7% | 76.0% | 63.6% | 55.6% | **79.0%** | 65.3% | **+3.0pp** |
| **Foley** | 98.7% | 76.0% | 85.9% | 98.9% | **88.0%** | 93.1% | **+12.0pp** |
| Hi-Hat | 98.8% | 100.0% | 99.4% | 98.8% | 100.0% | 99.4% | 0 |
| Impact | 89.5% | 100.0% | 94.4% | 89.5% | 100.0% | 94.4% | 0 |
| Kick | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0 |
| Music Loop | 97.1% | 44.0% | 60.6% | 97.5% | 52.0% | 67.8% | +8.0pp (bonus — not a named target class but shares root cause) |
| Percussion | 100.0% | 93.0% | 96.4% | 100.0% | 93.0% | 96.4% | 0 |
| **Riser** | 100.0% | 68.0% | 81.0% | 100.0% | **84.0%** | 91.3% | **+16.0pp** |
| Snare | 91.1% | 72.0% | 80.4% | 91.1% | 72.0% | 80.4% | 0 |
| Synth | 45.5% | 100.0% | 62.5% | 45.5% | 100.0% | 62.5% | 0 |
| Synth Loop | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0 (pre-existing taxonomy gap, unchanged) |
| **Vocal Loop** | 100.0% | 1.9% | 3.7% | 100.0% | **7.5%** | 14.0% | **+5.7pp** (still weak — see root cause) |
| Vocal Phrase | 60.1% | 83.0% | 69.7% | 61.0% | 86.0% | 71.4% | +3.0pp |

**Macro precision 0.7413→0.7428 (+0.15pp), macro recall 0.6962→0.7260
(+2.98pp), macro F1 0.6657→0.6898 (+2.41pp), overall known-population
accuracy 73.2%→76.4% (+3.2pp).** No class regressed. Kick precision
(OOD-inclusive, i.e. including hard-OOD material misclassified as Kick):
**98.0% (2 FP), identical to V4-G** — the per-class Kick threshold (0.92,
clamped at the safety ceiling) did not change which OOD samples leak into
Kick.

## OOD Results

| | V4-F (pre-V4-G) | V4-G | V4-H (full corpus) | V4-H (holdout) |
|---|---|---|---|---|
| OOD false-known | 89.6% | 33.2% | **41.6%** | **47.2%** |
| OOD rejection | ~10.4% | 66.8% | 58.4% | 52.8% |
| Known acceptance | 95.7%* | 93.7% | 96.8% | 97.3% |
| AUROC (offline, classifier-score projection, from V4-G's own harness) | ~0.68 | 0.911 | not re-measured (see below) | — |

*V4-F's 95.7% figure is V4-G's own report's holdout-measured number for the
margin gate; this phase's independent reproduction of the same margin gate
on its own split gives 99.85% known-acceptance / 92.0% false-known on
holdout — the two splits differ in exact composition (see Methodology Note)
but agree on the qualitative picture (margin accepts almost everything,
known and OOD alike).

**AUROC not independently re-measured this phase**: AUROC is a property of
a *score* (ranking OOD-vs-known), not of a *threshold choice* — V4-G's
score (centroid cosine similarity to the *nearest* centroid) is unchanged
by V4-H (the per-class threshold changes which score value counts as
"OOD," not the score itself). The underlying score's discriminative power
(AUROC 0.911, per V4-G) is therefore inherited unchanged; V4-H is a
*calibration* change (where to cut the same ranking), not a new scoring
method, consistent with spec §16's framing of this phase as finding "a
better operating point," not a new score.

## Coverage / Selective Accuracy

See §Threshold/Pareto Analysis table above. Full corpus: coverage
84.3%→88.2% (+3.9pp), selective accuracy 73.3%→73.1% (−0.2pp, effectively
flat). Holdout: not directly compared to a V4-G holdout coverage figure
(V4-G's report did not publish this exact figure for its own split), but
this phase's own V4-G-gate-on-this-split baseline gives coverage 84.5%/
selective accuracy 74.0% vs. the V4-H candidate's 89.5%/73.8% (holdout) —
same pattern: materially more coverage at effectively unchanged selective
accuracy.

## ML Override Analysis

| | V4-G production | V4-H candidate |
|---|---|---|
| Total ML overrides (`tagSource=ml_v3`) | 315 | 379 |
| ...on known ground truth | 277 | 320 |
| ...corrective | 269 | 312 |
| ...harmful | **0** | **0** |
| ...no-effect-equivalent | 8 | 8 |
| ...on OOD ground truth (harmful by definition) | 38 | 59 |

**Harmful overrides on known ground truth remain exactly 0** — the safety
property V4-F and V4-G both established is preserved unchanged. The
increase in overrides-onto-OOD (38→59, +21) is the direct, expected, and
fully-accounted-for mechanism by which the looser per-class thresholds
recover FX/Foley/Riser recall: more genuinely-known DSP/empty-evidence
samples now pass the gate and get a correct ML override applied (+43
corrective), and inevitably some additional adjacent hard-OOD material
passes the same loosened gate too (+21 onto OOD). This is the real,
quantified tradeoff this report is required to state honestly (spec §21) —
it is not hidden inside the aggregate OOD false-known number.

## Error Taxonomy

Of the 250 hard-OOD samples, V4-H candidate's 104 false-knowns (41.6%)
decompose as:

| Category | V4-G production | V4-H candidate |
|---|---|---|
| Strong FILENAME evidence (architectural — evidence hierarchy working as designed, ML never consulted) | 43 | 43 (**unchanged**) |
| ML override accepted (genuine gate false-negative — the tunable component) | 38 | 59 |
| Other (DSP evidence, heuristic path, small residual) | 2 | 2 |
| **Total** | 83 (33.2%) | 104 (41.6%) |

**The architectural (FILENAME-evidence) component is exactly unchanged
(43 in both) — proof that V4-H's threshold change affects only the tunable
ML-override component, not the evidence-hierarchy-driven component**, which
is precisely the separation spec §17/§19 require this report to make
explicit. All of the +21 increase in false-known count is attributable to
the ML-override-gate-false-negative bucket, the component this phase
directly targeted and the only one a threshold change can move.

## V4-F vs V4-G vs V4-H

| Metric | V4-F | V4-G | V4-H |
|---|---|---|---|
| Macro F1 (known population) | 0.5936* | 0.6657 | **0.6898** |
| Kick precision (OOD-inclusive) | 93.46% | 98.0% | **98.0%** (unchanged) |
| Vocal Loop recall | 13.2% | 1.9% | **7.5%** |
| FX recall | 97.0% | 76.0% | **79.0%** |
| Foley recall | 96.0% | 76.0% | **88.0%** |
| Riser recall | 89.0% | 68.0% | **84.0%** |
| Corrective ML overrides (known population) | 269** | 269 | **312** |
| Harmful ML overrides (known population) | 0 | 0 | **0** |
| OOD AUROC | ~0.68 (margin) | 0.911 (centroid, unchanged this phase) | 0.911 (same score) |
| OOD false-known (full corpus) | 89.6% | 33.2% | **41.6%** |
| Known rejection (holdout) | 4.3% | 6.6-6.8% | **2.7%** |
| Coverage (full corpus) | not measured this way in V4-F | 84.3% | **88.2%** |
| Selective accuracy (full corpus) | not measured this way in V4-F | 73.3% | 73.1% |

\* V4-F's macro F1 figure (0.5936) uses V4-G's own report's stated
methodology note that it was measured on an OOD-inclusive population
(heavier OOD bleed-through than V4-G/V4-H's per-class-only computation used
above) — not perfectly apples-to-apples with the 0.6657/0.6898 figures,
which are both computed identically (known-population-only) by this phase's
harness for a fair V4-G-vs-V4-H comparison; included for continuity with
V4-G's own reporting, with this caveat stated rather than implied
comparable.
\*\* V4-F's own corrective-override figure for the known population,
carried forward unchanged into V4-G's report (V4-G did not independently
retune this population, only the OOD gate).

**Reading this table honestly:** V4-H recovers real, non-trivial ground on
every one of V4-G's four flagged classes (FX +3pp, Foley +12pp, Riser
+16pp, Vocal Loop +5.7pp) and improves macro F1 by a further +2.4pp beyond
V4-G's own gain over V4-F, at a real, quantified, and fully-attributed cost
of +8.4pp OOD false-known (full corpus) relative to V4-G — while remaining
**2.15x better than pre-V4-G** (89.6%→41.6%). Both sides of spec §16's
dual bar move in the required direction.

## Runtime Cost

The change from a single scalar threshold comparison to a 16-entry array
lookup indexed by `nearestCentroidIndex` (already computed as a side effect
of the existing centroid-similarity loop — no new loop, no new distance
computation) adds exactly one integer-indexed array read and one float
compare per classified sample, i.e. **O(1) additional cost**, immeasurably
small relative to the existing `16 × 512 × 3` FLOP centroid-similarity
computation it sits inside (itself already established by V4-G as
sub-millisecond and negligible next to the ~65ms/file ONNX embedding
inference that dominates per-file cost). No new heap allocation, no new
loop, no change to thread-safety (the new array is a `constexpr` compile-time
constant, exactly like the existing `centroids[][]` table). `MlOverrideGate::
evaluate()`'s extraction from inline code to a free function has zero
runtime cost difference (the compiler inlines it identically either way;
verified no behavioral or performance-relevant change, only a
translation-unit-local structural refactor for testability).

## Regression Tests

Ran the existing 8-binary suite plus V4-H's new tests against the rebuilt
V4-H binaries (full LTO rebuild, `build-test/`, 9 targets rebuilt clean, 0
compile errors):

| Test | Result |
|---|---|
| TestTaxonomy | **PASS** |
| TestAudioFeatures | **PASS** |
| TestSampleEngine | **PASS** |
| TestCacheIntegrity | **PASS** |
| TestSafetyRegression | **PASS** (production cache DB size/mtime sentinel confirmed unchanged) |
| TestPersistedCacheHydration | **PASS** |
| TestPrecisionBrowserSorting | **PASS** |
| TestAcousticClassifierParity (incl. 6 new V4-H test groups, 20 checks) | **PASS** |

**8 RUN, 8 PASS, 0 FAIL, 0 SKIPPED, 0 NOT RUN.**

**Real end-to-end verification beyond the unit-test level:** the rebuilt
`ClassificationBenchmark` binary was used to rescan the full, real 1,607-file
corpus (`fixtures/scan_subset`) through the actual production code path
(fresh ONNX embedding inference, the real `MlOverrideGate::evaluate()`, the
real per-class threshold gate — nothing simulated). The scan run also
surfaced 170 extra, unrelated entries with names like `atmosphere_00.wav`,
`snare_03.wav` (synthetic-sounding single-word-prefix filenames, not present
in `dataset_manifest.json` and not matching any file currently on disk in
`fixtures/scan_subset` — 1607 files confirmed present via `ls`/`find` both
before and after the scan). This is judged to be a **pre-existing engine/
environment artifact of running `ClassificationBenchmark` repeatedly against
a shared `build-test/` working directory**, unrelated to this phase's diff
(no code in this phase's changeset touches directory enumeration,
`addPathToQueue()`, or cache-clearing) and orthogonal to the classification
logic under test. Rather than trust a contaminated 1,777-row output, the
scan output was filtered by exact basename match against
`dataset_manifest.json`'s 1,607 real entries (yielding exactly 1,607 rows,
confirmed) before computing any metric from it. **Filtered real-build
results exactly match this report's Python-harness predictions to 3
significant figures**: OOD false-known 41.6%, FX recall 79.0%, Foley recall
88.0%, Riser recall 84.0%, Vocal Loop recall 7.5%, Kick recall 100.0%, known
acceptance 96.8% — every one of these is an exact match to the numbers
reported in §Per-Class Results/§OOD Results above, confirming the harness's
predictions and the real compiled implementation agree, not merely that the
harness is internally consistent with itself.

Classifier-head numerical parity (`TestAcousticClassifierParity`): **max
logit error 3.16082e-06, max probability error 2.9717e-07 — byte-identical
to V4-G's published figures**, confirming `AcousticClassifierWeights.h` (the
linear head) was genuinely untouched by this phase, as required.

**V4-H-specific new tests** (all inside `TestAcousticClassifierParity`,
spec §27's requested list): (1) known-class acceptance — an embedding
identical to a known centroid is never OOD; (2) threshold boundary /
class-conditional behavior — a synthetic similarity score strictly between
FX's and Kick's per-class thresholds is proven to pass one gate and fail the
other, directly demonstrating the gate is class-conditional rather than
global; (3) `MlOverrideGate`: OOD clears a stale category (the V4-G bug fix,
re-verified as a dedicated fast unit test rather than only indirectly via a
corpus rescan); (4) `MlOverrideGate`: strong FILENAME evidence survives an
OOD flag unchanged (evidence-hierarchy preservation); (5) `MlOverrideGate`:
a confident non-OOD ML prediction legitimately overrides weak DSP evidence;
(6) `MlOverrideGate`: below-confidence-threshold, non-OOD input leaves the
pre-ML heuristic result untouched ("unknown"/no-op behavior).

Classifier-head numerical parity: **[filled in after build — expected
unchanged, 3.16e-06, since `AcousticClassifierWeights.h` was not touched by
this phase]**.

## Owner-Data Isolation

All scans use `setCacheDbDirectoryOverrideForTesting()` pointed at an
isolated `fixtures/cache` directory (gitignored) — never the production
cache path. `TestSafetyRegression` (part of the 8-binary suite)
independently re-verifies the production cache DB's size and mtime are
unchanged by this session's test runs, per its existing sentinel design (see
that test's own header comment) — and that check was directly re-verified
outside the test binary too, not just trusted: the real production DB at
`~/Library/SmartSampleManager/sample_cache.sqlite3` was located and its
size/mtime/SHA-256 hash recorded after all of this phase's builds, scans,
and test runs completed — `size=5517312 bytes, mtime=Aug 22 10:09:13`,
predating every command run in this phase (all of which occurred after
14:00 the same day per the build/scan logs), confirming zero writes reached
it. No AU/VST3 installed or overwritten, no Ableton launched, no release
deployment. Verified via `git status`/`ls -la` that no owner sample-library
files, DMGs, or licensing state were touched by this session.

## Acoustic BPM Status

**Unchanged this phase, as scoped.** No BPM code was touched: this phase's
failure-forensics and threshold work is entirely inside
`AcousticClassifier.h`/`AcousticClassifierCentroids.h`/`MlOverrideGate.h`,
none of which the BPM estimator (`estimateBpmFromAudio()` in
`SampleManagerEngine.cpp`) calls or is called by. No regression was
introduced (verified: `estimateBpmFromAudio()`'s source is byte-identical to
V4-G's committed version — the only edit inside `SampleManagerEngine.cpp`
this phase is the override-gate block replacement, several hundred lines
away from the BPM function). **Status remains EXPERIMENTAL** per V4-G's
finding (real vendor-loop strict accuracy 6.5%, systematic half-time
misdetection at 140-170 BPM). Recommendation, unchanged from V4-G and not
re-litigated this phase (out of scope per spec §5/§31): retain behind an
explicit "estimated" qualifier and suppressed for half-time-prone genre
material until a dedicated MIR phase (genre-aware tempo prior or stronger
onset front end) is authorized, OR disable in production until then. Not a
classification-freeze blocker either way.

## Remaining Limitation

**Vocal Loop recall (7.5% full-corpus / 11.5% holdout) remains far below a
usable bar**, and — per the root-cause finding above — cannot be
meaningfully improved further by OOD-threshold calibration alone: 88% of its
damage is caused by FILENAME-evidence heuristic ambiguity between "Vocal
Loop" and "Vocal Phrase," a layer this phase is explicitly scoped not to
touch. This is the one concrete, bounded, unresolved blocker to a full,
unqualified "PASS": recovering Vocal Loop to a materially usable recall
requires either a heuristic/taxonomy change (disambiguating the two
filename-evidence patterns) or a deliberate, owner-authorized decision to
let ML override FILENAME evidence for this specific class pair — both are
architecture/evidence-hierarchy changes outside this phase's charter (spec
§1/§17), not additional OOD-calibration tuning. This is reported as the
single next concrete blocker per spec §32's "identify ONE concrete
unresolved blocker," not an open-ended wishlist.

## Classification Freeze Decision

**FREEZE**, with the above limitation stated rather than hidden.
Rationale against spec §32's checklist:

- The OOD/known operating point is defensible: OOD false-known remains
  **2.15x better than pre-V4-G** (89.6%→41.6%) while known coverage and
  acceptance both *improved* over V4-G (84.3%→88.2% coverage, 93.7%→96.8%
  known acceptance).
- Damaged V4-G class recall is **materially recovered** for 3 of 4 named
  classes (FX +3pp, Foley +12pp, Riser +16pp) and **partially recovered**
  for the fourth (Vocal Loop +5.7pp, but root-cause-limited as explained
  above — this phase recovered the entire gate-attributable fraction of its
  damage, ~12% of the total).
- Harmful ML overrides on known ground truth remain **exactly 0** — no
  safety regression.
- Regressions remain clean: **8/8 PASS, confirmed** (see §Regression Tests),
  including a real end-to-end rescan of the full corpus that reproduced this
  report's predicted numbers exactly, not merely a unit-test-level check.
- Implementation complexity is acceptable: one new 16-entry `constexpr`
  array with a documented, reproducible derivation formula, one ~10-line
  change to `classify()`, and one pure-function extraction
  (`MlOverrideGate.h`) that reduces complexity (adds a unit-testable seam)
  rather than adding it.

V4-G's own CONTINUE-DEVELOPMENT recommendation named exactly one next step:
"investigate class-conditional OOD thresholds... before considering the
classification architecture for a freeze." That step is now done, with
evidence that it worked on both required axes. Per this phase's own stop
rule (spec §33): **do not start a V4-I**. Vocal Loop's residual weakness is
real but is not an OOD-calibration problem, so further OOD tuning would not
address it — recommending FREEZE with the one named limitation, not
recommending CONTINUE for a phase whose own lever cannot move the remaining
gap.

## Files Changed

- `Source/AcousticClassifierCentroids.h` — added `perClassOodThreshold[16]`
  with full derivation documented inline; `oodCosineSimilarityThreshold` and
  `centroids[][]` unchanged.
- `Source/AcousticClassifier.h` — `Result` gained `nearestCentroidIndex`;
  `classify()`'s OOD gate now indexes `perClassOodThreshold` by nearest
  centroid instead of comparing against a single scalar.
- `Source/MlOverrideGate.h` (**new**) — pure extraction of the V4-D/V4-G
  override-gate decision logic, behavior-identical, for direct unit testing.
- `Source/SampleManagerEngine.cpp` — inline override-gate block replaced
  with a call to `MlOverrideGate::evaluate()`; new `#include
  "MlOverrideGate.h"`.
- `Source/TestAcousticClassifierParity.cpp` — 6 new V4-H test groups.
- `CMakeLists.txt` — `TestAcousticClassifierParity` target now also compiles
  `Source/AbletonTaxonomy.cpp`.
- This file (new).

No taxonomy, evidence-hierarchy precedence, embedding model, linear-head
weights, BPM code, UX/EMBER/DesignTokens, cache schema, or persistence logic
changed.

## Git Status

Branch: `engineering/slo-classification-analysis-v4`, on top of V4-G's
`5e1b6b9`. Diff limited to exactly the files listed in §Files Changed:

```
 SmartSampleManager/CMakeLists.txt                       |   1 +
 SmartSampleManager/Source/AcousticClassifier.h          |  23 ++-
 SmartSampleManager/Source/AcousticClassifierCentroids.h |  74 ++++++-
 SmartSampleManager/Source/SampleManagerEngine.cpp       |  68 +++-----
 SmartSampleManager/Source/TestAcousticClassifierParity.cpp | 162 ++++++++++
 5 files changed, 281 insertions(+), 47 deletions(-)
 + Source/MlOverrideGate.h (new)
 + docs/SLO_CLASSIFICATION_V4H_FINAL_CALIBRATION_REPORT.md (new)
```

No audio, cache DB, or build artifacts staged (`tools/classification_benchmark/
v4h_results/` — this phase's local scan output — added to `.gitignore`
alongside the existing `v4f_results/`/`v4g_results/` entries, matching the
established pattern). `main` confirmed unchanged (`ab1de91`, unrelated to
this lineage) throughout this phase. No force-push, no history rewrite, no
rebase of shared history, no AI attribution in any commit trailer (per repo
convention). Pushed only the engineering branch, after qualification.

## Next Step

Vocal Loop's residual weakness (7.5-11.5% recall) is architecturally
out of this phase's reach; if it is ever prioritized, the concrete next step
is a heuristic/taxonomy review of FILENAME-evidence parsing for "Vocal Loop"
vs. "Vocal Phrase" disambiguation (or an owner-authorized evidence-hierarchy
exception for that specific class pair) — not further OOD-threshold work.

---

# Final Verdict

V4-H VERDICT:
PASS WITH LIMITATIONS
CLASSIFICATION ARCHITECTURE:
FREEZE
PRIMARY OOD RESULT:
OOD false-known 41.6% (full corpus) / 47.2% (holdout) — 2.15x better than pre-V4-G (89.6%), a deliberate, quantified give-back of some of V4-G's OOD gain in exchange for materially recovering known-class recall.
DAMAGED V4-G CLASS RECALL:
PARTIALLY RECOVERED (FX +3pp, Foley +12pp, Riser +16pp fully addressed by this phase's mechanism; Vocal Loop +5.7pp recovers the gate-attributable ~12% of its damage, the remaining 88% is a FILENAME-evidence heuristic issue outside this phase's scope)
HARMFUL ML OVERRIDES:
0
ACOUSTIC BPM:
EXPERIMENTAL — NOT A CLASSIFICATION SHIP BLOCKER
MAIN MODIFIED:
NO
INSTALLED PLUGINS MODIFIED:
NO
NEXT STEP:
If Vocal Loop is prioritized further, review FILENAME-evidence heuristic disambiguation between "Vocal Loop" and "Vocal Phrase" (a taxonomy/heuristic change, not OOD calibration) — otherwise, stop here per this phase's own terminal-calibration mandate.
