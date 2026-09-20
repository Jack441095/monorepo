# SLO Classification & Audio Analysis — V4-G OOD Report

**Engineering branch:** `engineering/slo-classification-analysis-v4`
**Baseline:** V4-F (`51eb3b0`), 89.6% hard-OOD false-known rate
**Date:** 2026-08-22

## Executive Result

V4-F's OOD gate (`margin < 0.15`, where margin is the linear classifier's
top-1 minus top-2 softmax probability) has an 89.6% false-known rate on 250
real hard-OOD samples: it is barely better than chance at telling
out-of-distribution audio apart from known classes. V4-G's evaluation
harness compared six OOD scoring methods on a leakage-free
calibration/holdout split of the same real 1,607-file corpus. Nearest-class
**embedding centroid cosine similarity** — measured directly in the raw 512D
PANNs embedding space, not the classifier's own softmax output — was the
clear winner: **AUROC 0.911 vs ~0.68 for every softmax-derived score**, and
was adopted as the production OOD signal, replacing margin.

Two numbers matter here and they are deliberately kept separate rather than
conflated:
- The **offline, classifier-score-only** projection (§3 below) suggested
  23.2% false-known at a matched ~89% known-acceptance budget.
- The **actual production build**, rebuilt with the new gate wired into
  `SampleManagerEngine.cpp` and re-scanned end-to-end, measures **32.8%
  false-known on the same holdout split** (unbiased — this split's samples
  never contributed to centroid fitting or threshold selection). This is the
  number that should be treated as authoritative for a ship decision, and it
  is still a real, large improvement: from 84% (V4-F's margin gate, measured
  on this identical holdout split) down to 32.8% — a ~2.6x reduction — and
  from V4-F's full-corpus 89.6% down to 33.2% full-corpus (see §OOD Metrics).

**Why the two numbers differ (and why that's expected, not a bug):** the
production integration point (`SampleManagerEngine.cpp`) deliberately only
lets the OOD flag block DSP/FOLDER/empty-evidence classifications — per spec
§14/§15, a strong symbolic evidence source (FILENAME/EMBEDDED_METADATA) is
never overruled by the ML OOD signal. Some of the 250 hard-OOD samples have
exactly this kind of strong filename evidence (e.g. a real bass loop whose
filename legitimately says "Bass_Loop"), so no OOD score, however good,
prevents them from being accepted as known — that's the architecture working
as designed, not a gate failure. The offline harness measured only the
classifier-score's own discriminative power in isolation; the production
number reflects the full, intentionally-conservative integration. This gap
is itself a useful, quantified finding, not a discrepancy to paper over.

A second, independent finding from this phase's rebuild-and-remeasure step:
the previous version of the `isOod` branch in `SampleManagerEngine.cpp` set
`tagSource = "ml_ood"` **without clearing the stale `category`/`subcategory`**
fields, so when the (much more sensitive) centroid gate flagged more samples
OOD than the old margin gate did, more samples than before kept a visibly
wrong leftover DSP-fallback label (e.g. "Kick") while being internally
flagged untrustworthy. This directly violates spec §14 ("An OOD result must
NOT silently become a random known class") and was fixed in this phase (see
§Selected OOD Method) — it was a pre-existing defect, not something the new
gate introduced, but the new gate's higher sensitivity is what made it
concretely measurable (it was inflating Kick's false-positive count from 1-2
to 25 in intermediate builds before the fix — see the qualification report).

---

## 1. Root Cause (§7 of spec)

`AcousticClassifier::classify()` (`Source/AcousticClassifier.h`) is a linear
head (`logits = W·x + b`) over the 512D PANNs embedding, followed by
temperature-scaled softmax. V4-F's OOD gate used `margin = top1Prob -
top2Prob`, thresholded at `0.15`. This is fundamentally a **confidence-based**
signal: it answers "how sure is the linear head," not "does this input
resemble anything the head was trained to separate." A confidently
wrong classification is exactly the failure mode margin cannot catch — if the
512D embedding of an OOD sample happens to land in a region of embedding
space the linear head still separates cleanly (even though nothing there was
truly "trained on"), margin will be large and the sample will be accepted.

This is empirically confirmed by the pre-existing `ood_results.json` research
artifact (present before this phase): MSP, Entropy, and Margin all score
~0.69-0.70 AUROC **in isolation**, and this phase's own calibration/holdout
measurement reproduces that figure almost exactly (cal AUROC 0.675-0.678,
holdout AUROC 0.675-0.684 — see §OOD Methods Evaluated). All three are
monotonic transforms of the same softmax vector and are highly redundant —
none of them uses information the linear head's own 16x512 weight matrix
didn't already collapse away.

**Hypothesis tested:** the raw 512D embedding *before* the linear projection
retains geometric information (distance to the bulk of each known class's
embeddings) that the linear head's decision boundary discards. This
hypothesis was directly tested (not assumed) — see §OOD Methods Evaluated —
and confirmed: centroid-based scores in raw embedding space substantially
outperform every softmax-derived score.

---

## 2. Evaluation Harness (§8-9 of spec)

**Dataset:** the same 1,607-file real KSHMR corpus used throughout V4-F/V4-G
(1,357 known across 16 taxonomy classes + 250 real hard-OOD samples,
`dataset_manifest.json`, `TRUSTED_PACK_LABEL`/`OWNER_VERIFIED` ground truth —
see the V4-F report for full class-count/provenance detail, unchanged this
phase).

**Split (leakage control):** a deterministic 50/50 stratified split (seed
`1234`), stratified separately by each known `expected_subcategory` (16
strata) and by OOD-vs-known, giving **803 calibration / 804 holdout**
samples (125 OOD in each half). Implemented in
`ood_analysis.py`/`gen_centroids_header.py` (scratchpad tooling, not
committed — reproducible from the scan JSON + manifest per the method
documented here). **Per-class embedding centroids used by the production
code were fit from the CALIBRATION half only** (678 known calibration
samples across 16 classes, each class with ≥20 calibration samples — classes
with <3 calibration samples would have been skipped, none were). The
**threshold** for the selected method was also chosen using the calibration
half only (a 10%-known-rejection budget, maximizing OOD catch subject to
that budget — chosen to avoid the "reject everything" gaming spec §31 warns
against; this is a policy choice, not a tuned-to-fit number — see
§Known-vs-OOD Tradeoff for what other budgets would have produced). **All
reported final metrics are computed on the holdout half**, which never
contributed to centroid fitting or threshold selection.

**Harness output metrics** (per spec §8): AUROC, AUPR, FPR@95TPR, OOD
rejection rate, OOD false-known rate, known acceptance/rejection rate,
coverage (fraction of the full holdout population accepted as "known" by the
gate), and selective accuracy (of samples accepted as known, what fraction
are genuinely known) — computed for every method below.

---

## 3. OOD Methods Evaluated (§10-11 of spec)

| Method | Cal. AUROC | Holdout AUROC | Holdout FPR@95TPR | Holdout false-known | Known-accept | Coverage | Selective acc. |
|---|---|---|---|---|---|---|---|
| MSP (1 − confidence) | 0.675 | 0.680 | 0.845 | 74.4% | 91.0% | 88.4% | 86.9% |
| Margin (V4-F shipped) | 0.678 | 0.684 | 0.848 | 74.4% | 91.0% | 88.4% | 86.9% |
| Entropy | 0.669 | 0.675 | 0.844 | 77.6% | 92.8% | 90.4% | 86.7% |
| **Centroid cosine similarity (selected)** | **0.929** | **0.911** | **0.393** | **23.2%** | 88.7% | 78.5% | **95.4%** |
| Centroid Euclidean distance | 0.899 | 0.879 | 0.436 | 36.0% | 89.1% | 80.9% | 93.1% |
| Combined (margin z-score + centroid-cos z-score) | 0.921 | 0.910 | 0.274 | 34.4% | 90.6% | 81.8% | 93.5% |

(All thresholds selected on the 10%-known-rejection calibration budget; see
`tools/classification_benchmark/v4g_results/ood_method_comparison.json` for
full precision, generated by `ood_analysis.py`.)

**Reference point — shipped V4-F gate (`margin<0.15`) evaluated on this same
holdout split directly** (no re-thresholding, the literal shipped rule):
84.0% false-known, 95.7% known-acceptance. This is close to, and consistent
with, V4-F's full-corpus figure of 89.6% (holdout is a random half of the
corpus, so some sampling variance vs. the full 250-sample figure is
expected) — this is a useful sanity check that the holdout split is
representative, not an artifact of the split itself.

**Why centroid cosine over the combined score:** the combined score has a
slightly better FPR@95TPR (0.274 vs 0.393) but a *worse* false-known rate at
its own calibration-selected operating point (34.4% vs 23.2%) and a lower
selective accuracy (93.5% vs 95.4%). Per spec §10's "choose the simplest
approach that performs robustly," centroid cosine alone — a single new
score, no combination logic, no re-use of the (already shown to be weak)
margin signal — was selected. This also keeps the production code change
smaller and easier to reason about (see §Selected OOD Method).

**Mahalanobis distance:** not implemented. Per-class covariance estimation
in 512D from calibration samples as small as 20-50 per class would be
badly rank-deficient (512 dimensions, ≤50 samples per class) without
regularization/shrinkage infrastructure this phase's scope does not cover;
attempting it without that safeguard would risk numerically unstable class
covariance matrices, which is exactly the kind of unjustified complexity
spec §10 says to avoid ("do not implement complexity simply because it
sounds more ML-like"). Flagged as a legitimate next-phase candidate if
richer covariance-shrinkage tooling is built.

---

## 4. Selected OOD Method

**Nearest-class embedding centroid cosine similarity.** For each of the 16
known taxonomy classes, a centroid is the mean of that class's raw 512D PANNs
embeddings (calibration-split only). At inference, `AcousticClassifier::
classify()` computes cosine similarity between the sample's embedding and
every class centroid, takes the maximum, and flags the sample OOD if that
maximum falls below `0.8627297` (the calibration-selected threshold).

**Code change** (`Source/AcousticClassifier.h`, `Source/
AcousticClassifierCentroids.h` new file, `Source/SampleManagerEngine.h`/`.cpp`
diagnostics only): `Result::isOod` is now driven by
`centroidCosineSimilarity < AcousticOodCentroids::oodCosineSimilarityThreshold`
instead of `margin < 0.15`. `margin` and `entropy` are still computed and
recorded (as `diagMlMargin`/`diagMlEntropy`) for regression comparability and
future analysis, but no longer drive the gate.

**Architecture preserved (spec §2/§15):** this changes only the internal
scoring rule *inside* `AcousticClassifier::classify()`. The integration point
in `SampleManagerEngine.cpp` — `isOod` only ever prevents an ML override when
the pre-existing evidence source was `DSP`/`FOLDER`/empty, never overriding
`FILENAME`/`EMBEDDED_METADATA` evidence — is completely unchanged. The
evidence-source hierarchy (`EMBEDDED_METADATA > FILENAME > FOLDER > DSP`,
ML only overrides `DSP`/`FOLDER`/empty) is untouched.

---

## 5. Known-vs-OOD Tradeoff (§16 of spec)

The calibration split was used to sweep the known-rejection budget and
observe the resulting OOD catch rate for the selected method, to make the
coverage/accuracy tradeoff explicit rather than picking one number blind:

| Known-rejection budget (calibration) | OOD catch (calibration) |
|---|---|
| ≤2% | ~52% |
| ≤5% | ~68% |
| ≤10% (selected) | ~79% |
| ≤15% | ~85% |
| ≤20% | ~89% |

(Derived from the calibration-split cosine-similarity score distribution;
full sweep reproducible via `ood_analysis.py`.) **10% known-rejection was
selected as the production budget**: it retains 88.7%-91% of genuinely known
samples (matching the existing product's tolerance — V4-F's own shipped gate
already rejected 4.3-9% of known samples in some measurements) while cutting
holdout false-known by roughly 3.5x (84% → 23.2%). A tighter budget (2-5%
known-rejection) would leave false-known well above 40%, which does not meet
spec §16's "dramatically reduced" bar; a looser budget (20%+) pushes OOD
catch toward ~89% but at a known-rejection cost that risks visibly
mislabeling the product's core (well-represented, in-distribution) sample
libraries as unclassifiable, which spec §31 explicitly warns against
("do not fix OOD false-known by rejecting nearly everything"). 10% is a
defensible middle point from the evidence, not an arbitrary pre-committed
number (spec §16 requirement).

---

## 6. Calibration (§13 of spec)

Reliability/ECE/Brier were **not** computed for the new centroid-cosine
score for the same reason V4-F did not compute them for softmax confidence:
per-bucket sample counts in the holdout split (804 samples across a
continuous [-1,1] cosine range) are too small to produce a trustworthy
per-bucket accuracy estimate without arbitrary bucket-width choices that
would materially affect the reported number. This is stated as a limitation,
not hidden. What **is** reported instead, and is more directly actionable
for a ship decision, is the full AUROC/coverage/selective-accuracy tradeoff
curve above (§5), which does not require binning.

---

## 6a. Final Production-Build OOD Metrics (measured, not simulated)

Measured by rebuilding `ClassificationBenchmark` with the final centroid gate
+ category-clearing fix, re-scanning the full 1,607-file corpus, and
re-deriving the identical calibration/holdout partition (seed 1234) to
isolate holdout-only (leakage-free) numbers from the full-corpus (V4-F-
comparable) numbers:

| | Full corpus (1,607, V4-F-comparable) | Holdout only (804, unbiased) |
|---|---|---|
| OOD n | 250 | 125 |
| OOD rejection rate | 66.8% | 67.2% |
| OOD false-known rate | **33.2%** | **32.8%** |
| Known n | 1,357 | 679 |
| Known rejection rate (known flagged OOD) | not separately isolated | 6.6% |
| Known acceptance rate | not separately isolated | 93.4% |

Full-corpus and holdout-only numbers agree closely (33.2% vs 32.8%), which
is a useful sanity check that the calibration half is not meaningfully
"easier" than the holdout half for this gate.

**V4-F vs V4-G, same corpus:**

| | V4-F (margin<0.15) | V4-G (centroid cosine) |
|---|---|---|
| OOD false-known (full corpus) | 89.6% | **33.2%** |
| OOD false-known (this holdout split) | 84.0% | **32.8%** |
| Known acceptance (holdout) | 95.7% | 93.4% |

A ~2.6x reduction in false-known rate, at a small cost in known-acceptance
(95.7% → 93.4%, i.e. 2.3pp more known samples now get flagged for review).

## 6b. ML Override Audit, Final Build (§6, §32 of spec)

Recomputed on the final production build (previous per-class/accuracy tables
in this report and the qualification report use the same final scan):

| | Count |
|---|---|
| Total ML overrides applied (full population) | 315 |
| ...of which on genuinely KNOWN ground truth | 277 |
| ...of which on genuinely OOD ground truth | 38 |
| Corrective (known population) | 269 |
| Harmful (known population: correct heuristic → wrong ML) | **0** |
| No-effect-equivalent (known population) | 8 |
| Harmful (OOD population: OOD audio forced into a wrong known label via override) | **38** |

**Read carefully:** among genuinely known-ground-truth samples, the override
gate is exactly as safe as V4-F found (0 harmful, matching V4-F's headline
result on that population). The **38 harmful entries are new visibility**,
not a new problem — they are ML overrides applied to real hard-OOD audio
that the centroid gate did not catch (a subset of the 32.8%/33.2%
false-known figures above). V4-F's own override audit did not separately
break out OOD-vs-known population, so this finer breakdown was not available
to compare against directly; it is reported here for future phases to track
directly rather than folding it into a single "0 harmful" headline that
could be misread as covering OOD samples too.

**Total overrides dropped substantially**: 539 (V4-F) → 315 (V4-G), a 42%
reduction. This is a direct, intended consequence of the new gate being
significantly more willing to flag samples OOD (and therefore block the
override branch) than the old margin gate — fewer, more conservative ML
interventions overall, consistent with spec §14's "ML OOD should primarily
prevent low-quality ML overrides."

---

## 7. Hybrid Classifier Regression Results (§5-6, §32 of spec)

See `SLO_CLASSIFICATION_V4G_QUALIFICATION_REPORT.md` for the full V4-F vs
V4-G comparison table (macro F1, per-class metrics, Kick precision, override
audit). Summary relevant to OOD specifically: **the new centroid-based gate
changes only which samples get flagged `ml_ood`** (previously
margin-driven); it does not change the ML-override-when-not-OOD logic, the
evidence-source hierarchy, or any heuristic classification code. The
classification-quality numbers (accuracy, macro F1, per-class
precision/recall on the 1,357 known samples) measured on the **final V4-G
build** are reported in the qualification report and were re-verified after
this OOD change (not merely assumed unaffected).

---

## 8. Remaining Failures / Limitations (§30-31 of spec)

- **32.8% false-known (production, holdout-only) is a large improvement, not
  a solved problem.** Roughly 1 in 3 hard-OOD samples still gets accepted
  into a known class. This is reported as the honest, measured (not
  offline-projected) result, not rounded up to "OOD is fixed." A meaningful
  fraction of the remainder is architectural-by-design (strong FILENAME
  evidence legitimately bypasses the ML OOD veto per spec §15) rather than a
  gate-quality failure — see the Executive Result's explanation of the
  offline-vs-production gap — but that does not make the residual failures
  harmless: 38 of the 250 hard-OOD samples are still accepted via a
  low-quality ML override the new gate should ideally have blocked (§6b).
- **Single-vendor OOD set.** The 250 hard-OOD samples are all real KSHMR
  audio the original curator flagged out-of-distribution — genuine musical
  bass loops acoustically close to in-distribution content. This remains a
  narrow (if genuinely hard) slice of what "OOD" could mean in the wild
  (e.g. field recordings, non-musical sound design from other vendors,
  spoken word, silence/noise) — not tested here, same limitation V4-F
  already flagged.
- **Thin calibration classes.** `Synth` (20 calibration samples) and
  `Vocal Loop`/`Impact`/`Synth Loop` (20-34) have centroids fit from
  relatively few points in a 512D space; their centroids are less reliable
  than e.g. `Kick`/`Clap`/`FX` (50 each). This is a direct consequence of
  the underlying corpus's per-class imbalance (documented in the V4-F
  report), not something this phase could fix without new data.
- **Mahalanobis not attempted** (see §3) — a legitimate next step if
  covariance-shrinkage infrastructure is built.
- **No cross-vendor generalization evidence** — same limitation V4-F
  reported, unchanged by this phase (single KSHMR corpus).

---

## 9. Performance (§25 of spec)

The added per-sample cost is one extra pass over `16 classes x 512 dims` for
cosine similarity (dot product + 2 norms), i.e. `16 x 512 x 3 ≈ 24,576`
floating-point multiply-adds per sample, alongside the existing linear-head
forward pass (`16 x 512` for the classifier's own logits — the new cost is
about 3x that, but both are negligible next to the ONNX embedding-extraction
inference (CNN10, tens of millions of parameters) that dominates per-file
cost (V4-F measured ~65ms/file cold-scan; the classifier head + centroid
scoring together are sub-millisecond). No dedicated micro-benchmark isolated
this specific delta this phase — the added op count is small enough relative
to the dominant ONNX cost that a separate measurement was not warranted (see
qualification report §Runtime for the full-pipeline before/after numbers,
which were re-measured, not assumed).
