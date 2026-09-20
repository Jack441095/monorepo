# SLO L-05 Review Packet Work Package V1

## Package record

- **ID/title:** `SLO-L05-REVIEW-PACKET-V1` — fail-closed reviewed-data intake
- **Product/system:** SLO acoustic classification research/evidence lane
- **Owner/worktree:** NITE DSP engineering; `workspace/worktrees/slo/slo-build-entry-v1`
- **Base SHA:** `ba2c5e515bce54bc52334da0b9934d71081d943a`
- **Status:** tooling complete; human review and any model change remain open

## Objective and finding

Make the next accuracy step operational for an owner or reviewer. A scan only
measures the current classifier; it does not teach it. The missing bridge was a
controlled way to turn known-set conflicts and OOD false accepts into a
reviewable, provenance-bound packet without copying private audio or silently
changing labels.

## Files changed

- `tools/classification_benchmark/build_l05_review_packet.py`
- `tools/classification_benchmark/test_build_l05_review_packet.py`
- `tools/classification_benchmark/apply_l05_review_results.py`
- `tools/classification_benchmark/test_apply_l05_review_results.py`
- `docs/classification/SLO_CLASSIFIER_IMPROVEMENT_PLAYBOOK_V1.md`
- this report

The tool reads a declared manifest, `owner_review_queue.csv`, and
`error_database.csv`, then writes three new CSVs: a label-free reviewer view,
a separate key for adjudication, and a blank results template. It resolves by
path identity where available, rejects ambiguity, requires a source SHA-256,
deduplicates by source SHA, and refuses to overwrite output.

The intake tool validates the completed template with two named reviewer
decisions, explicit disagreement handling, and source SHA/path coherence. It
emits reviewed annotations and an intake receipt while leaving the original
manifest and production state untouched.

## Direct verification

Command:

```bash
python3 -m unittest -v \
  SmartSampleManager/tools/classification_benchmark/test_build_l05_review_packet.py \
  SmartSampleManager/tools/classification_benchmark/test_validate_l05_qualification_package.py \
  SmartSampleManager/tools/classification_benchmark/test_research_v3_reporting.py
```

Result: **25 tests passed**.

The tool was also run against the current candidate evidence snapshot:

- 1,607 manifest rows, including 250 OOD rows;
- 50 known-set review-queue rows;
- 163 OOD error rows;
- 213 unique review candidates after source-SHA deduplication;
- no audio copied, decoded, hashed, or modified;
- no production model, weights, thresholds, taxonomy, or OOD policy changed.

The 213-row count is an evidence snapshot, not a target dataset size.

## Security, privacy, and evidence boundaries

- Audio remains at its existing path; the tool writes metadata only.
- The key retains current/proposed labels separately from the reviewer view.
- Manifest identity ambiguity fails closed rather than guessing by basename.
- Existing output is preserved by refusing overwrite.
- The tool cannot create an independent-review receipt and does not qualify a
  release by itself.
- Reviewers must record rights/owner authorisation, reviewer IDs,
  disagreements, adjudication, and final sign-off separately.

## Remaining limitations and decisions

- No independently reviewed labels have been supplied yet.
- Existing folder/vendor labels remain evidence candidates, not ground truth.
- The current external Energy scan is still paused for CPU protection and has
  no receipt.
- A human owner must decide which candidates are legitimate taxonomy classes,
  `UNKNOWN`, or OOD before any training or calibration.
- A candidate must improve the frozen holdout and not regress weak classes,
  unseen vendors/source families, or OOD safety before promotion.

## Rollback

Remove or revert this isolated worktree commit if the packet format is not
accepted. No product data or runtime state needs restoration because this
package performs metadata-only reads and writes new outputs only.

## Next package

Run the reviewed-data loop: obtain independent labels for the packet, record
adjudication and authorisation, complete the full-corpus scorecard, and compare
one candidate retraining/recalibration run with the frozen production baseline.
