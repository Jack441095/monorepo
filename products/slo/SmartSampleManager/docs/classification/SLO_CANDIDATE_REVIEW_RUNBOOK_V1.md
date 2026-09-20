# SLO candidate review runbook v1

This runbook is for the current 388-file candidate queue. It is deliberately
review-first: no step below renames, moves, deletes, or rewrites source audio.

## 1. Label independently by ear

The blind session is already available at `http://127.0.0.1:8781`.

If it needs to be started on a fresh port:

```bash
cd /Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/slo/SmartSampleManager/tools/classification_benchmark
python3 label_tool.py \
  --manifest label_manifest_candidate_suggestions_388_blind_v1.json \
  --port 8781 \
  --csv verified_candidate_suggestions_388.csv
```

The manifest hides the model prediction. The label CSV is the independent
source of truth for this review pass.

## 2. Audit the session

```bash
cd /Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/slo
python3 SmartSampleManager/tools/classification_benchmark/audit_local_labellers.py \
  --ports 8781 \
  --out SmartSampleManager/tools/classification_benchmark/results_candidate_suggestions_labeller_audit_live.json
```

Do not continue if the server is unreachable or the CSV/manifest identities do
not match.

## 3. Join labels into owner decisions

```bash
python3 SmartSampleManager/tools/classification_benchmark/import_blind_labels_to_owner_decisions.py \
  --queue SmartSampleManager/tools/classification_benchmark/owner_review_queue_breadth_candidate_v1.csv \
  --manifest SmartSampleManager/tools/classification_benchmark/label_manifest_candidate_suggestions_388_blind_v1.json \
  --labels SmartSampleManager/tools/classification_benchmark/verified_candidate_suggestions_388.csv \
  --reviewer OWNER_NAME \
  --out SmartSampleManager/tools/classification_benchmark/owner_review_queue_breadth_candidate_reviewed.csv
```

Exact agreement becomes an approval candidate; disagreement is rejection; skip
or uncertainty is deferred. This command does not grant approval.

## 4. Emit the independent approval receipt

```bash
python3 SmartSampleManager/tools/classification_benchmark/build_explicit_approval_receipt.py \
  --collection SmartSampleManager/tools/classification_benchmark/review_collections_breadth_candidate_v4_evidence.json \
  --duplicate-guard SmartSampleManager/tools/classification_benchmark/results_full_taxonomy_breadth_candidate_duplicate_guard_v3_similarity_gate.json \
  --decisions SmartSampleManager/tools/classification_benchmark/owner_review_queue_breadth_candidate_reviewed.csv \
  --out SmartSampleManager/tools/classification_benchmark/results_full_taxonomy_breadth_candidate_approval_reviewed.json
```

The receipt remains blocked for disagreement, deferral, duplicate flags, path
changes, source-signature changes, or edited model evidence.

## 4a. No-ear-label AI evidence review

For label-free triage, load the named evidence packet into the localhost
workspace. This exposes suggestions and proposed filenames, but serves no
audio and performs no writes:

```bash
python3 SmartSampleManager/tools/classification_benchmark/review_workspace_server.py \
  --collections SmartSampleManager/tools/classification_benchmark/review_collections_breadth_candidate_v4_evidence.json \
  --feedback-log /tmp/slo_name_feedback.jsonl \
  --evidence-packet SmartSampleManager/tools/classification_benchmark/receipts/gpu0_evidence_packet_full_named_8621_20260913.json \
  --port 8765
```

Filename decisions are submitted as typed append-only events through
`POST /api/feedback` (`accept_name_candidate`, `correct_name_candidate`, or
`reject_name_candidate`). After review, build the advisory precision report:

```bash
python3 SmartSampleManager/tools/classification_benchmark/build_label_free_name_calibration.py \
  --packet SmartSampleManager/tools/classification_benchmark/receipts/gpu0_evidence_packet_full_named_8621_20260913.json \
  --feedback /tmp/slo_name_feedback.jsonl \
  --out SmartSampleManager/tools/classification_benchmark/receipts/name_calibration_review.json
```

The report uses Wilson lower bounds and never authorizes renames. A slice can
only become an owner-approved promotion candidate after it has enough reviewed
decisions and independently passes the project’s existing approval gate.

## 5. Validate only; do not apply

```bash
python3 SmartSampleManager/tools/classification_benchmark/apply_rename_plan.py \
  SmartSampleManager/tools/classification_benchmark/full_taxonomy_breadth_candidate_suggest_plan_testing_v3_similarity_gate.jsonl \
  --include-suggest --approve-suggest --approve-auto \
  --duplicate-guard SmartSampleManager/tools/classification_benchmark/results_full_taxonomy_breadth_candidate_duplicate_guard_v3_similarity_gate.json \
  --approval-gate SmartSampleManager/tools/classification_benchmark/results_full_taxonomy_breadth_candidate_approval_reviewed.json
```

Without `--apply`, this is a dry run. Applying anything requires a separate,
explicit owner decision after inspecting the receipt and dry-run output.

## Current baseline

- 388 suggestions, 0 owner decisions, 0 approval-ready rows.
- 82 duplicate-risk flags remain blocked regardless of human agreement.
- Source audio and filenames have not been modified.
