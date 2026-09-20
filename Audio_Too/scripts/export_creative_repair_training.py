#!/usr/bin/env python3
"""Export reviewed Creative Lab repair records for future KENN training."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRAINING_DIR = ROOT / "studio" / "kenn" / "kenn" / "artifacts" / "training"
DEFAULT_RAW = TRAINING_DIR / "creative_lab_repair_records.jsonl"
DEFAULT_REVIEWS = TRAINING_DIR / "creative_lab_repair_reviews.json"
DEFAULT_APPROVED = TRAINING_DIR / "creative_lab_repair_records.approved.jsonl"
DEFAULT_MANIFEST = TRAINING_DIR / "creative_lab_repair_records.approved.manifest.json"

sys.path.insert(0, str(ROOT / "studio" / "kenn"))
from kenn.training.training_records import iter_jsonl_raw, write_jsonl  # noqa: E402


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_jsonl(path: Path) -> tuple[list[dict], int]:
    """Parse ``path`` as JSONL, counting (rather than raising on) malformed
    rows. This intentionally does NOT use the strict, raise-on-first-error
    ``read_jsonl`` in kenn.training.training_records: the skipped-row count
    returned here is itself part of this tool's health signal (see
    ``validate_export``, which reports a nonzero skip count as a validation
    error rather than crashing), so a bad row needs to be countable, not
    fatal. It still shares the actual line-parsing logic via
    ``iter_jsonl_raw``.
    """
    records = []
    skipped = 0
    for _lineno, _raw_line, row, error in iter_jsonl_raw(path):
        if error is not None:
            skipped += 1
            continue
        row["record_id"] = str(row.get("record_id") or f"{row.get('feedback_id', '')}:{row.get('run_created_at', '')}")
        records.append(row)
    return records, skipped


def load_reviews(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    reviews = data.get("reviews")
    return reviews if isinstance(reviews, dict) else {}


def reviewed_records(records: list[dict], reviews: dict[str, dict], decision: str) -> list[dict]:
    rows = []
    for record in records:
        review = reviews.get(record.get("record_id", ""))
        if not isinstance(review, dict) or review.get("decision") != decision:
            continue
        rows.append({**record, "review": review, "review_decision": decision})
    return rows


def summarize(records: list[dict], reviews: dict[str, dict]) -> dict:
    review_counts: dict[str, int] = {}
    label_counts: dict[str, int] = {}
    for record in records:
        label = str(record.get("label") or "unknown")
        label_counts[label] = label_counts.get(label, 0) + 1
        review = reviews.get(record.get("record_id", ""))
        decision = str(review.get("decision") if isinstance(review, dict) else "unreviewed")
        review_counts[decision] = review_counts.get(decision, 0) + 1
    return {"records": len(records), "review_counts": review_counts, "label_counts": label_counts}


def build_manifest(
    *,
    raw_path: Path,
    reviews_path: Path,
    output_path: Path,
    decision: str,
    records: list[dict],
    selected: list[dict],
    skipped: int,
    reviews: dict[str, dict],
) -> dict:
    summary = summarize(records, reviews)
    selected_summary = summarize(selected, {record["record_id"]: record.get("review", {}) for record in selected})
    return {
        "schema": "kenn.creative_repair_dataset_manifest.v1",
        "created_at": iso_now(),
        "raw_path": str(raw_path),
        "reviews_path": str(reviews_path),
        "output_path": str(output_path),
        "decision": decision,
        "raw_records": len(records),
        "selected_records": len(selected),
        "skipped_rows": skipped,
        "review_counts": summary["review_counts"],
        "label_counts": summary["label_counts"],
        "selected_label_counts": selected_summary["label_counts"],
    }


def write_manifest(path: Path, manifest: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_manifest(path: Path) -> tuple[dict, str]:
    if not path.exists():
        return {}, f"Manifest missing: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, f"Manifest is invalid JSON: {exc}"
    if not isinstance(data, dict):
        return {}, "Manifest root is not an object."
    return data, ""


def validate_export(output_path: Path, manifest_path: Path, expected_decision: str = "approved") -> tuple[bool, list[str]]:
    errors = []
    records, skipped = read_jsonl(output_path)
    manifest, manifest_error = load_manifest(manifest_path)
    if manifest_error:
        errors.append(manifest_error)
    if not output_path.exists():
        errors.append(f"Output missing: {output_path}")
    if skipped:
        errors.append(f"Output JSONL has {skipped} skipped row(s).")
    if manifest and manifest.get("schema") != "kenn.creative_repair_dataset_manifest.v1":
        errors.append("Manifest schema is not kenn.creative_repair_dataset_manifest.v1.")
    if manifest and manifest.get("decision") != expected_decision:
        errors.append(f"Manifest decision is {manifest.get('decision')!r}, expected {expected_decision!r}.")
    if manifest and int(manifest.get("selected_records", -1)) != len(records):
        errors.append(f"Manifest selected_records={manifest.get('selected_records')} but output has {len(records)} row(s).")
    for record in records:
        if record.get("review_decision") != expected_decision:
            errors.append(f"Record {record.get('record_id', '<missing>')} is not marked {expected_decision}.")
    return not errors, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export reviewed Creative Lab repair records for KENN training.")
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW, help="Raw Creative Lab repair JSONL.")
    parser.add_argument("--reviews", type=Path, default=DEFAULT_REVIEWS, help="Review sidecar JSON.")
    parser.add_argument("--output", type=Path, default=DEFAULT_APPROVED, help="Output JSONL path.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Output manifest JSON path.")
    parser.add_argument("--decision", choices=["approved", "needs_work", "rejected"], default="approved")
    parser.add_argument("--summary-only", action="store_true", help="Print counts without writing output.")
    parser.add_argument("--validate", action="store_true", help="Validate the exported JSONL against its manifest.")
    args = parser.parse_args()

    if args.validate:
        ok, errors = validate_export(args.output, args.manifest, args.decision)
        if ok:
            print(f"Valid {args.decision} repair dataset: {args.output}")
            return 0
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    records, skipped = read_jsonl(args.raw)
    reviews = load_reviews(args.reviews)
    summary = summarize(records, reviews)
    selected = reviewed_records(records, reviews, args.decision)

    print(f"Raw records: {summary['records']} ({skipped} skipped)")
    print(f"Review counts: {json.dumps(summary['review_counts'], sort_keys=True)}")
    print(f"Label counts: {json.dumps(summary['label_counts'], sort_keys=True)}")
    print(f"{args.decision} records: {len(selected)}")
    if args.summary_only:
        return 0
    write_jsonl(args.output, selected, sort_keys=True)
    manifest = build_manifest(
        raw_path=args.raw,
        reviews_path=args.reviews,
        output_path=args.output,
        decision=args.decision,
        records=records,
        selected=selected,
        skipped=skipped,
        reviews=reviews,
    )
    write_manifest(args.manifest, manifest)
    print(f"Exported {len(selected)} records to {args.output}")
    print(f"Wrote manifest to {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
