# Correction-Log Review Queue — Runbook (QC-03, 2026-09-18, branch slo/class-opt-v1)

## What was proven (demo, synthetic data only)
- Bridge `ingest_cpp_correction_log.py --log <corrections.jsonl> --output-dir ...`
  runs read-only and FAILs CLOSED on bad records (caught non-SHA hash + numeric
  version fields during this pass — both rejected before any output).
- Demo ingest: **4 pending, READY_FOR_OWNER_REVIEW, automatic_promotion=false**,
  `paths_missing=4` (expected — /tmp demo paths don't exist on disk).
- Outputs: `pending_corrections_review.csv/.json` + `top_confusions_demo.json`
  (Percussion→Foley 1, Percussion→Hi-Hat 1, Kick→Kick Loop 1 — mirrors the real
  residual confusions: Foley↔Percussion, Perc/Hi-Hat).

## Production use (real user corrections)
1. Corrections land at `~/Library/Application Support/SLO/corrections.jsonl`
   (append-only, paths + metadata, NO audio — `Source/CorrectionLog.h`).
   Currently absent on this machine (verified `ls` → no such file) = zero real
   corrections to review yet.
2. Run: `ingest_cpp_correction_log.py --log ~/Library/.../corrections.jsonl
   --output-dir validation/class-opt-v1/correction-review-<date>/`
   (never overwrites existing outputs; never promotes labels).
3. Review the CSV, aggregate top confusions weekly ("top confusions this week"),
   feed into gate/queue prioritisation (QC-02).
4. Promote into the dataset only via the explicit owner import path
   (`build_owner_approved_training_manifest.py` + sealed holdout rerun).

## Kill criterion
- Drop/pause the queue if owner overturn rate > 30% (reviewers disagree with
  corrections) or if corrections skew to a single vendor/pack (leakage risk).

## Why this matters
- Programme measurement: by-ear labels are the ONLY intervention that ever
  improved SLO on unseen libraries (+3.29pp / −17.9pp false-accept per 500).
  This queue is the cheapest pipe from deployment distribution back to labels.
