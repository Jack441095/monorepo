# SLO factorised classification benchmark v1

Date: 2026-09-12

## Decision

The factorised head is **not promoted**. It did not clear the pre-registered +2 percentage-point accuracy gate against the frozen centroid incumbent. The factorised evidence architecture is retained in shadow mode because it gives the product a stable place to record physical measurements, identity/form claims, uncertainty, provenance, and later taxonomy changes without changing current rename behaviour.

## Protocol

- Training corpus: `corpus_v4b_escape_recovered.npz`.
- Training manifest: `factorised_training_manifest_v1.json`.
- The sealed class-conditional validation manifest was excluded before fitting: 15 overlapping paths were removed.
- Exact duplicate aliases were removed from the remaining training rows: 1,525 canonical rows from 80 collections.
- The benchmark retained 27 classes with at least five examples from at least five collections (1,495 rows).
- Evaluation used five collection-grouped splits and five fixed seeds.
- The baseline was nearest-centroid classification on the same frozen features. The candidate was the factorised head trained on the same rows and folds.
- The run used the existing remote Anaconda/PyTorch environment on physical GPU 1. No host or GPU restart was performed.

## Results

| model | accuracy | macro-F1 | accuracy SD |
| --- | ---: | ---: | ---: |
| frozen nearest centroid | 55.130% | 47.855 | 0.078pp |
| factorised head | 55.425% | 48.617 | 0.279pp |

The observed gain is +0.295pp accuracy and +0.762 macro-F1. It is well below the +2pp promotion gate, so there is no evidence that this head improves the production classifier on unseen collections.

## What is retained

The new `AudioEvidence` record is decision-neutral shadow data. It preserves the legacy taxonomy alongside structured identity and form claims, physical measurements, metadata, model versions, duplicate-group provenance, and confidence/alternatives. The record is refreshed after the existing heuristic and acoustic passes, but it is not persisted, used for policy, or used to rename files yet.

This keeps the next experiments comparable and prevents a promising schema change from being mistaken for a validated classifier improvement.

## Next experiment gate

Do not request another broad labelling batch solely because this head missed the gate. The next useful work is to use the shadow records to test independent attribute heads and evidence-calibrated fusion on a fresh, collection-held-out slice. New labels are justified only for a pre-registered ambiguity or taxonomy decision that the existing sealed set cannot answer.

