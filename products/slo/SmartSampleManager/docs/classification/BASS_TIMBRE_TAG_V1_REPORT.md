# SLO Bass Timbre Tag (808 / Reese) V1 Report

**Generated for:** Fine-Grained Subcategorization V1, Phase 9 (part of the SLO producer-taxonomy expansion).

## Method

84 real, filename-labeled files across 7 vendors (60x "808", 24x "Reese" — unambiguous, standard producer terms, not a judgment-call label). Extracted 512D PANNs embeddings via the existing scan pipeline (no new inference code — reuses what every other classification path already computes). Deterministic 50/50 stratified calibration/holdout split (seed=1234), same discipline as the production OOD centroids (`AcousticOodCentroids.h`): centroids computed from the calibration half only, accuracy reported from the holdout half only — no leakage.

## Result

**Holdout accuracy (leakage-free): 92.9% (39/42).**

An earlier leave-one-out estimate on the full 84-sample set gave 95.2% — reported here as the honest, lower, non-leaked number instead, since LOO on a set that also contributed to the pool the "nearest neighbor" is drawn from is a weaker guarantee than a true held-out split.

**Honest limitation found during calibration**: per-sample confidence margin (top1 vs top2 centroid similarity) does **not** cleanly separate correct from wrong predictions at this sample size — the lowest-margin wrong prediction (0.0019) and a correct prediction with similarly low margin (0.0024) overlap. A margin-based "only tag if confident" gate would not meaningfully improve precision here, so this ships as: always compute and return the label plus a confidence score, and let downstream callers/UI decide how to present it (same posture as `tagConfidence` elsewhere in this engine) — not a hard binary gate.

## Implementation

- `BassTimbreCentroids.h` — generated centroids, calibration-half only.
- `BassTimbreClassifier.h` — independent nearest-centroid cosine-similarity classifier. Does not read or modify anything `AcousticClassifier`/`MlOverrideGate` touch, does not participate in the frozen production linear head or its per-class OOD thresholds.
- Wired into `SampleManagerEngine::runInferenceBatch()`, gated on `subcategory == "Bass One-Shot" || "Bass Loop"`, appending `"808"` or `"Reese"` to `secondaryTags`.
- `TestBassTimbre` regression test: each class's own centroid classifies as itself with near-1.0 confidence (guards against a future centroid-regeneration mistake, e.g. swapped class order — does not re-derive the full accuracy number, which lives here instead).

## Scope limitations

- **Reese class is thin** (24 total samples, 12 in the calibration half). V4-H's own thin-class caution (n=20-27 needing shrinkage for per-class OOD thresholds) applies in spirit here too — this is a real, working signal, not a finished, maximally-robust one. More Reese examples across more vendors would strengthen it.
- Only these two labels exist right now. Other real bass timbre types producers care about (Sub, Distorted/Growl, Synth Bass generally) are not covered — same "measure before you build" methodology applies if/when those are added; see the parent plan's Phase 11.
- Vendor concentration: Reese samples lean toward fewer vendors than 808 (IMANU contributes a large share) — cross-vendor generalization for Reese specifically is less proven than for 808.
