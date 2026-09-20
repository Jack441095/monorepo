# Breadth-trained full-taxonomy model candidate

The 1,850-row breadth corpus has been frozen into a separate nearest-centroid
model candidate. The existing production/full-taxonomy artifacts were not
overwritten.

## Model evidence

- 28 eligible classes, 1,832 training rows, 81 collections
- Vendor-held-out OOF accuracy: 55.98% ± 0.76%
- Confidence gate at 95% precision: 0.740, 11.9% OOF coverage
- Similarity gate at 95% precision: 0.731, 9.0% OOF coverage
- Model artifact: `tools/classification_benchmark/full_taxonomy_model_breadth_v1.npz`
- Metadata: `tools/classification_benchmark/full_taxonomy_model_breadth_v1.json`

## Full-library review-only projection

The candidate model was run over the existing 7,315-file embedding cache. This
is a derived prediction/review operation; files were not decoded again or
modified.

| action | count |
|---|---:|
| suggest (Clap/Kick/Snare candidate tier) | 583 |
| review | 6,728 |
| never_act | 4 |
| auto_rename | 0 |

The duplicate guard identified 235 exact canonical rows, 335 exact aliases,
and 510 acoustic near-duplicate flags. The approval gate blocked all 583
suggestions, and the apply validator selected zero rows.

Prediction and safety receipts:

- `tools/classification_benchmark/full_taxonomy_breadth_candidate_predictions_testing_v1.jsonl`
- `tools/classification_benchmark/full_taxonomy_breadth_candidate_suggest_plan_testing_v1.jsonl`
- `tools/classification_benchmark/results_full_taxonomy_breadth_candidate_duplicate_guard_v1.json`
- `tools/classification_benchmark/results_full_taxonomy_breadth_candidate_approval_gate_v1.json`

Canonical regenerated queue after the provenance fix:

- `tools/classification_benchmark/full_taxonomy_breadth_candidate_suggest_plan_testing_v2.jsonl`
- `tools/classification_benchmark/results_full_taxonomy_breadth_candidate_duplicate_guard_v2.json`
- `tools/classification_benchmark/results_full_taxonomy_breadth_candidate_approval_gate_v2.json`
- `tools/classification_benchmark/review_collections_breadth_candidate_v2.json`

The canonical candidate-embedding tool was also corrected to read both legacy
and current old-model field names. Its regenerated receipt reports 3,444
actual old-model disagreements (rather than silently reporting zero), making
model-change diagnostics trustworthy:

- `tools/classification_benchmark/full_taxonomy_breadth_candidate_predictions_testing_v4.jsonl`

The 583 suggestions were also exported into an action-specific, immutable
review collection for UI/manual inspection:

- `tools/classification_benchmark/review_collections_breadth_candidate_v1.json`

It contains no transferred labels, no approvals, and no applied actions.

The model is therefore a deployable candidate, not an active production model.
Promotion still requires explicit owner approval and the independent guards in
the review packet.

## Factorised-head probe

The new corpus also received a three-seed, five-fold probe of the shared
identity/family/form head. It underperformed the centroid control:

| method | accuracy | macro-F1 |
|---|---:|---:|
| centroid control | 55.82% | 47.78 |
| factorised head | 54.53% | 45.89 |

The factorised head is therefore not promoted. Its receipt is
`tools/classification_benchmark/results_breadth_factorised_head_probe_v1.json`.

## Physical-feature fusion

The 22 physical waveform features were also tested as a controlled fusion arm
on the same 1,832-row, 81-collection grouped benchmark. The best tested weight
was effectively neutral: **+0.03 percentage points** versus embedding-only
accuracy, with no meaningful macro-F1 improvement. This route is closed as a
classifier improvement for this checkpoint; physical features remain valuable
for explanations, search, and taxonomy review.

Receipt: `tools/classification_benchmark/results_breadth_physical_feature_fusion_v1.json`

## Similarity-gated action projection

The plan generator now accepts the calibrated 0.731 similarity floor as a
second action gate. On the same 7,315-file projection this reduced candidate
suggestions from 583 to **388**, with 6,923 reviews and four never-act rows.
Among suggestions, duplicate checks found 50 acoustic near-duplicates, 14
exact canonical rows, and 18 exact aliases. All 388 remain blocked pending
approval; the apply validator selected zero rows.

Receipts:

- `tools/classification_benchmark/full_taxonomy_breadth_candidate_suggest_plan_testing_v3_similarity_gate.jsonl`
- `tools/classification_benchmark/results_full_taxonomy_breadth_candidate_duplicate_guard_v3_similarity_gate.json`
- `tools/classification_benchmark/results_full_taxonomy_breadth_candidate_approval_gate_v3_similarity_gate.json`
- `tools/classification_benchmark/review_collections_breadth_candidate_v3_similarity_gate.json`

The current 388-item review tier now has a joined physical-evidence packet:
all 388 rows include a definition card, nearest labelled reference, aspect
similarity, filename evidence, and the explicit human-approval requirement.

- `tools/classification_benchmark/review_evidence_breadth_candidate_v1.jsonl`
- `tools/classification_benchmark/review_collections_breadth_candidate_v4_evidence.json`
