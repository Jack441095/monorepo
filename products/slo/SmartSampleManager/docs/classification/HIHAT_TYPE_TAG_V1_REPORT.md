# SLO Hi-Hat Type Tag (Open / Closed) V1 Report

**Generated for:** Fine-Grained Subcategorization V1, Phase 11 — the recommended-next subtype from `SLO_PRODUCER_TAXONOMY_REQUIREMENTS_V1.md` ("open/closed hat is the strongest bet — sharp, well-known acoustic distinction, likely high separability").

## Method

103 real, filename-labeled files across 4 vendors (60x "Open", 43x "Closed" — unambiguous producer terms). Same discipline as the bass timbre tag: 512D PANNs embeddings via the existing scan pipeline, deterministic 50/50 stratified calibration/holdout split (seed=1234), centroids from calibration half only, accuracy from holdout half only.

## Result

**Holdout accuracy (leakage-free): 92.3% (48/52).** Consistent with the bass timbre precedent (92.9%) despite a much smaller raw separation margin in cosine-similarity terms — mean intra-class similarity 0.939 vs. inter-class 0.930 (a 0.009 gap, vs. bass timbre's 0.072 gap). Hi-hats are acoustically similar to each other overall (high baseline similarity across the whole class), but the 512-dimensional embedding space still carries enough signal for nearest-centroid classification to separate Open from Closed reliably.

## Implementation

Identical architecture to the bass timbre tag: `HiHatTypeCentroids.h` (calibration-half centroids) + `HiHatTypeClassifier.h` (independent nearest-centroid classifier, no dependency on the frozen production head or OOD thresholds), wired into `SampleManagerEngine::runInferenceBatch()` gated on `subcategory == "Hi-Hat"`, appending `"Open"`/`"Closed"` to `secondaryTags`. `TestHiHatType` regression test verifies each centroid classifies as itself.

## Scope limitations

- Vendor concentration: KSHMR and "Old Movies 1" contribute a large share of both classes — cross-vendor generalization beyond these specific vendors is less proven than the raw sample count suggests.
- Only Open/Closed exist. A third real category some producers use ("half-open"/pedal hi-hat) is not covered — same "measure before you build" methodology applies if that's wanted later.
- As with bass timbre, per-sample margin was not separately re-verified as a clean correct/wrong separator here — same posture: always compute and return a confidence score, let downstream UI decide how to present it, no hard binary confidence gate.
