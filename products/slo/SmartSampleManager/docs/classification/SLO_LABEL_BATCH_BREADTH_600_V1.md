# SLO Label Batch: Collection-Breadth 600

## Purpose

This is the next human-labeling batch after the completed class-conditional gate validation. It is designed to test the measured result that labels from unseen collections are worth more than additional labels from familiar collections.

## Receipt

- Input review receipt: `/tmp/slo_review_collections_full_v1.json`
- Source root: `/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing`
- Output manifest: `SmartSampleManager/tools/classification_benchmark/label_manifest_review_breadth_600_v1.json`
- Queue actions: `suggest`, `review`
- Items: 600
- Top-level collections represented: 33
- Selection: deterministic path ordering within each collection, round-robin across collections
- Prediction hints: hidden
- Audio state: read-only; no files were changed, renamed, moved, or deleted

## Live labeling session

The queue is currently served by the separate resumable labeler at
`http://localhost:8772`:

```sh
python3 tools/classification_benchmark/label_tool.py \
  --manifest tools/classification_benchmark/label_manifest_review_breadth_600_v1.json \
  --csv tools/classification_benchmark/verified_label_manifest_review_breadth_600_v1.csv \
  --port 8772
```

The earlier gate-validation session on port `8771` is a separate process and
its CSV is not reused.

## Label-free physical analysis

Before labels are entered, read-only definition cards have been extracted for
all 600 paths:

- Output: `tools/classification_benchmark/definition_cards_label_manifest_review_breadth_600_v1.json`
- Cards: 600 / 600
- Extraction errors: 0
- Contains measurable signal evidence only; it creates no semantic labels
- Manifest SHA-256 is recorded in the receipt and matches the queue

## Next measurement

After the queue is labelled, audit the CSV against this manifest, then retrain and evaluate with the collection-held-out protocol. Do not promote any class or enable automatic renaming from this batch alone; promotion still requires the existing owner-review and approval-gate receipts.
