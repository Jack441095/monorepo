# SLO waveform evidence fusion benchmark v1

Date: 2026-09-12

## Decision

Generic physical/waveform descriptors are **not promoted as a classifier input**. Concatenating 32 interpretable `physics_v1_1` measurements with the frozen embedding produced only a +0.23 percentage-point gain, well below the pre-registered +2pp gate. The descriptors remain valuable as an explanation layer and for narrowly defined mechanism rules (for example pitch glide, transient shape, beating, and sub-energy evidence).

## Protocol

- Inputs were the frozen `factorised_training_manifest_v1.json` and `corpus_v4b_escape_recovered.npz`.
- Exact duplicates and the sealed validation overlap were already removed by that manifest.
- The two long files whose first ten seconds are digital silence yielded no descriptor from the current extractor; they were explicitly excluded rather than represented as zeros.
- The resulting evaluation used 1,493 rows, 27 classes, and 80 collection groups.
- Five seeds and five `StratifiedGroupKFold` collection-held-out splits were used for every arm.
- Each fold fit its own feature standardisation and nearest-centroid classifier.
- No source audio was modified and no production model, cache, rename plan, or policy was changed.

## Results

| arm | accuracy | macro-F1 | accuracy SD |
| --- | ---: | ---: | ---: |
| frozen embedding | 54.762% | 47.548 | 0.502pp |
| waveform descriptors only | 34.642% | 29.378 | 0.642pp |
| embedding + waveform descriptors | 54.990% | 47.834 | 0.532pp |

The fused arm is +0.228pp accuracy and +0.286 macro-F1 versus the same-row embedding arm. This is not evidence for a production classifier change.

## Product implication

The physical analysis is still worth keeping because it answers a different question from the embedding: it can provide a checkable definition card such as “strong sub energy”, “downward pitch glide”, “sharp transient”, or “detuned beating”. Those claims can support review explanations, ambiguity routing, and future mechanism-specific heads. They should not be treated as a generic accuracy lever until a pre-registered, mechanism-focused experiment clears the same collection-held-out gate.

