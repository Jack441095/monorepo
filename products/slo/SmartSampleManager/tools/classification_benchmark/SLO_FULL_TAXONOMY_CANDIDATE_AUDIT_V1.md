# SLO full-taxonomy candidate audit — V1

Date: 2026-09-11

## Scope

The frozen full-taxonomy centroid model was run against the 7,315 files in the
`auto_rename,suggest` slice of the testing library. This is an inference audit
only. No audio was modified, renamed, moved, deleted, or uploaded.

## Integrity

- Candidate embeddings: `candidate_embeddings_testing_v1.npz`
- Rows: 7,315
- Embedding shape: 7,315 x 2,048
- Extraction errors: 0
- Missing source paths: 0
- Duplicate paths: 0
- Predictions: `full_taxonomy_candidate_predictions_testing_v1.jsonl`
- Every prediction action: `review`
- Frozen model: `full_taxonomy_model_v1.npz`

## Results

- Calibrated 95% gate: 438 files (6.0%)
- Old audio-model disagreements: 3,195 (43.6%)
- High-confidence disagreements: 4/438
- Filename evidence was present for 421/438 high-confidence rows; 417 agreed
  with the full-taxonomy class.
- High-confidence class distribution: Kick 309, Hi-Hat 64, Clap 36, Snare 28,
  Crash 1.

The model is strongly biased toward the well-supported drum classes on this
unseen library. The broad 3,195-row disagreement rate is not evidence that the
new model is better; it is evidence that the existing class-conditional
calibration does not yet qualify full-taxonomy auto-action on this domain.

## Additional grouped fusion result

On the labelled corpus, a fixed, pre-declared set of high-precision filename
tokens was evaluated inside the same collection-held-out folds. Audio-only
accuracy was 56.57%. Overriding low-confidence audio predictions with trusted
filename classes reached 63.00% at an audio-confidence cutoff of 0.70;
always using those filename classes reached 63.40%. The gain was positive in
all eight seeds, but the filename override precision was 86.55% and 91.13%
respectively, so this is a strong suggestion/fusion route—not yet a 95%
auto-rename route. The experiment is recorded in
`results_full_taxonomy_fusion_eval_v1.json`.

## Existing human-label audit

The two core human-label CSVs contain 502 consensus rows that align with the
eligible corpus taxonomy. A corrected collection-held-out audit trained on the
full corpus inside each fold and scored only those human rows across 78
collections:

| policy | accuracy | override precision |
| --- | ---: | ---: |
| audio only | 68.05% | — |
| filename if audio confidence < 0.70 | 78.54% | 92.66% |
| filename always (trusted classes) | 79.03% | 95.34% |

The aggregate override precision is encouraging, but class-level support and
lower confidence bounds are not yet sufficient to promote a broad auto-action
policy. The detailed receipt is `results_full_taxonomy_human_audit_v1.json`.
The trusted-token counts are: Kick 60/63, Hi-Hat 44/46, Snare 74/77, Clap
86/88, Crash 15/16, Percussion Loop 10/10, and Drum Loop 18/22. These raw
rates are useful for prioritising labels, but their 95% lower bounds still sit
below the auto-action bar.

## Decision

Do **not** apply the full-taxonomy model to rename files yet. The 438 rows are
exported to `full_taxonomy_high_confidence_review_v1.csv` for human checking.
They are a validation queue, not an approval list.

## Required next gate

Label a breadth-first, collection-held-out sample from this queue and from the
disagreement boundary. Re-estimate precision separately for every proposed
class and for every operating point. Only classes that pass the product
precision gate on unseen collections may enter an auto-rename policy. All
other classes remain review-only or rejection.
