# Breadth candidate rename dry run

This is a read-only end-to-end check of the conservative candidate tier on
the real testing library. It is not an approval and it did not rename, move,
copy, delete, or rewrite any audio.

## Run

- Root: `/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing`
- Sample: first 500 deterministic files
- Candidate classes recorded: Clap, Kick, Snare
- Auto-action was **not enabled**
- Model path: existing fusion classifier, with the product qualification gate
  left closed

## Results

| action | count |
|---|---:|
| never_act | 41 |
| review | 338 |
| suggest | 121 |
| auto_rename | 0 |

The duplicate guard flagged two acoustic near-duplicate suggestions. The
approval-gate audit blocked all 121 suggestions because they require explicit
owner approval. The apply validator then selected zero rows and exited in
dry-run mode.

Receipts:

- `tools/classification_benchmark/rename_plan_breadth_candidate_dryrun_500_v1.jsonl`
- `tools/classification_benchmark/results_rename_duplicate_guard_breadth_candidate_500_v1.json`
- `tools/classification_benchmark/results_rename_approval_gate_breadth_candidate_500_v1.json`

Safety status: source audio unchanged, production policy unchanged, approval
not granted, and zero rename actions executed.

## Thresholded dry run

The plan generator now accepts an optional, validated class-threshold file.
Using the measured candidate thresholds (without `--enable-auto`) produced 169
suggestions and 290 reviews in the same 500-file sample. The duplicate guard
again found two acoustic near-duplicates; all 169 suggestions remained blocked
by the approval gate, and the apply validator selected zero rows.

Threshold policy:

- `tools/classification_benchmark/class_thresholds_breadth_candidate_v1.json`
- `tools/classification_benchmark/rename_plan_breadth_candidate_thresholded_dryrun_500_v1.jsonl`
