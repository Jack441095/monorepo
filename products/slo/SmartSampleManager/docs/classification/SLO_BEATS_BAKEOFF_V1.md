# SLO BEATs public-backbone bake-off — V1

Date: 2026-09-11

## Decision

**Do not promote BEATs.** On the collection-held-out protocol it is much
worse than the current Perch+CLAP representation by itself, and adding it to
the incumbent is a small negative. The public-model route remains useful for
future auxiliary tags, but BEATs is not a classification or auto-renaming
improvement for SLO.

## Controlled result

The experiment used the existing verified-by-ear rows, the same content/path
order as `bioacoustic_emb.npz`, and 523 rows from 10 viable classes with at
least 15 examples (570 unique rows after path deduplication). This is a
controlled encoder bake-off, not a replacement for the newer v3 full-taxonomy
receipt. Repeated grouped folds held out whole vendors/collections. The
estimator was the current standardized, L2-normalized cosine nearest centroid;
no labels were added and no source audio was changed.

| representation | vendor-held-out accuracy | macro-F1 | paired delta vs incumbent |
|---|---:|---:|---:|
| Perch + CLAP (incumbent) | 64.90% ± 7.78 | 56.24% | — |
| BEATs | 47.30% ± 8.53 | 41.97% | −17.60pp |
| Perch + CLAP + BEATs | 63.33% ± 8.16 | 55.73% | −1.57pp |

The eight paired vendor seeds were `[-1.31, +0.34, -2.11, +1.23, -2.38,
-2.39, -5.63, -0.29]` percentage points for the combined representation;
only 2/8 seeds improved. It does not clear the project’s +2pp promotion gate.

For context, the same run produced 70.20% random-CV accuracy for the
incumbent and 70.79% for the combined representation. That small random-CV
gain is not evidence of product improvement; the vendor-held-out result is the
decision metric.

## Provenance and safety

- BEATs implementation: Microsoft’s official `unilm/beats` source.
- Checkpoint: `BEATs_iter3_plus_AS20K.pt`.
- Checkpoint SHA-256: `8008b126bb5e8ab08912c60c58847ed676d32e64a5864c922356b7c2522fb2f8`.
- Receipt: `SmartSampleManager/tools/classification_benchmark/results_beats_bakeoff_v1.json`.
- Extraction cache: `SmartSampleManager/tools/classification_benchmark/beats_embeddings_v1.npz`.
- The runner is `SmartSampleManager/tools/classification_benchmark/beats_bakeoff.py`.
- The checkpoint was used for research only and is not copied into production,
  model export, or the commercial application.
- The run was local CPU/MPS only. Remote GPU 1 was not contacted, restarted,
  killed, or modified.

## Interpretation

This is consistent with the earlier MERT/AST result: a model that is strong on
general AudioSet or musical audio is not automatically strong on short,
isolated sample-pack events. The binding problem remains taxonomy/domain
coverage and rejection calibration, not an untried generic encoder.
