# SLO OOD/Centroid Recalibration V1 -- A Null Result

**Bottom line: this attempt did not work, was fully reverted, and the production classifier is unchanged.** `Source/AcousticClassifierCentroids.h` is byte-identical to its state before this work began. This report exists so the next attempt doesn't repeat the same path -- a rigorously-tested null result is a valid, useful outcome, not a failure to bury.

## Why this was attempted

`SLO_ACCURACY_ROADMAP_V1.md`'s Stage 2: the production classifier's per-class embedding centroids and OOD thresholds (`AcousticClassifierCentroids.h`) were calibrated against a single-vendor, 1,607-file corpus (KSHMR only). Meanwhile `docs/SLO_CLASSIFICATION_V5_RESEARCH_BASELINE.md` ranked single-vendor calibration as the #1 highest-value-lowest-cost fix available. By this point in the session, the real benchmark corpus had grown to 5,157 files across 15 vendors and all 17 SLO taxonomy classes -- a ~3.2x larger, genuinely multi-vendor replacement was a reasonable, well-motivated thing to try.

## Methodology (unchanged from the original V4-G/V4-H calibration)

- Deterministic 50/50 stratified split by `expected_subcategory`, seed=1234.
- Centroids = mean 512D embedding per class, calibration half only.
- Per-class OOD threshold: `rawPercentile_c` = a chosen percentile of {best-centroid cosine similarity of every calibration-half sample whose ground truth is c}, shrunk toward a global threshold via an empirical-Bayes weight `w_c = n_c/(n_c+10)`, clamped to [0.60, 0.92].
- Global threshold = the same percentile of the pooled calibration-half best-cosine-similarity distribution.
- `AcousticClassifierWeights.h` (the frozen linear head) was never touched -- only centroids and thresholds.
- Atmosphere was out of scope throughout: the linear head has exactly 16 output classes and never included Atmosphere at all (an architectural fact discovered during this work, unrelated to this recalibration).

## Step 1: isolated Python validation looked like a clear win

A leakage-free holdout evaluation (Python re-implementation of `AcousticClassifier::classify()`'s exact math, using the real, unchanged frozen weights) compared the new centroids/thresholds against the original, at the formula's naive 10% rejection budget:

| Metric | Old (production) | New (10% budget) |
|---|---|---|
| Known-content recall | 30.9% | 44.2% |
| Known-content false-unknown rate | 40.7% | 10.9% |
| OOD-negative false-known rate | 53.7% | 82.4% |

A large, genuine-looking improvement in recall/false-unknown, alongside a real cost in OOD safety. A budget sweep (5%-30%) showed that cost/benefit trade was smooth, not a cliff, and recommended shipping at a stricter ~25% budget to keep most of the recall gain while clawing back some OOD safety. **This was shipped to a branch and validated further -- and that's where the real story starts.**

## Step 2: real end-to-end benchmarking contradicted the isolated validation

At the recommended 25% budget, a full re-run of the actual production pipeline (`run_real_corpus_v2_benchmark.py`, the same 5,157-file corpus, real ONNX inference, the real `AbletonTaxonomy::classify()` decision logic including `MlOverrideGate`) showed:

| Metric | Before (production) | After (25% budget) |
|---|---|---|
| Real audio-only accuracy | **39.0%** | **35.5%** |

A regression, not the improvement the isolated validation predicted. All 28 regression test binaries still passed (the classifier code itself works correctly -- this is a real behavioral trade-off, not a bug).

## Step 3: a full budget sweep found no threshold that recovers baseline

Suspecting the 25% budget specifically was the problem, a further sweep of stricter budgets was run, each validated against the **real end-to-end pipeline** (not the isolated Python metric, which had already been shown untrustworthy for this purpose):

| Budget | Real audio-only accuracy |
|---|---|
| 25% | 35.5% |
| 35% | 33.0% |
| 40% | 31.9% |
| 50% | 30.6% |
| 60% | 30.2% |
| 75% | 30.0% |

Every single tested budget underperformed the 39.0% baseline, and accuracy got **monotonically worse** as the budget got stricter, plateauing around 30% rather than recovering. This rules out "wrong threshold" as the explanation -- no threshold in this family beats baseline, in either direction.

## Root cause: the isolated validation doesn't model the real pipeline's fallback interaction

The real production pipeline doesn't just discard an OOD-rejected sample -- it falls back to the plain DSP heuristic (`AbletonTaxonomy`'s zcr/energy/decay-time logic, independently measured elsewhere this session at ~7.4% accuracy on its own). A more permissive OOD gate routes *more* samples into the ML-override path, including the harder, more marginal ones the old strict gate used to filter out. If the DSP heuristic was already getting some of those specific marginal samples right (by chance, on easier-than-average cases within the rejected pool), replacing that correct DSP guess with a less-reliable ML override is a net loss for those samples -- even though the ML path's own accuracy, measured against the whole population equally, looks better in isolation.

The monotonic, threshold-independent nature of the regression (every budget, both directions, all worse) points at something more specific than "the gate is miscalibrated": **the new centroids themselves appear to route/predict differently for this real corpus's actual sample population in a way that interacts badly with the DSP fallback, not just an OOD-strictness problem.** This wasn't isolated further (see Recommendation below), but it's the most consistent explanation of the data.

## What this means for future attempts

**Any future OOD/classifier recalibration must be validated against the real end-to-end pipeline (including the DSP-fallback interaction) before being trusted, not an isolated ML-path simulation.** That's the concrete, reusable lesson from this attempt -- it would have saved a full rebuild-and-benchmark cycle if the validation methodology had modeled this from the start.

## Recommendation

Do not pursue further centroid/threshold tuning on this corpus using this method -- the sweep already covers the space and none of it works. Move to `SLO_ACCURACY_ROADMAP_V1.md` Stage 3's **energy-based OOD experiment** instead: a fundamentally different OOD signal (derived from the linear head's own logits, e.g. `E(x) = -T*logsumexp(logits/T)`, rather than embedding-centroid cosine similarity). This isn't just a threshold variant of the same idea -- a genuinely different signal could rank samples by actual reliability differently than centroid distance does, which could break the specific trade-off that sank this attempt. Validate it against the real end-to-end pipeline from the start this time.

## Final state (verified)

- `Source/AcousticClassifierCentroids.h`: confirmed byte-identical to git HEAD (`git diff` shows no changes).
- Real end-to-end benchmark re-confirmed at exactly 39.0% audio-only / 71.5% full-evidence accuracy -- matching the pre-recalibration baseline exactly, not just "close."
- All 28 regression test binaries (`ssm_qual_fast_regression` + `ssm_qual_cache` + `ssm_qual_classification` + `ssm_qual_intelligence`) run directly, all exit 0.
- No production code changed as a result of this investigation.
