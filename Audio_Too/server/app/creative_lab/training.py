"""Creative Lab: training functions.

Split out of creative_lab.py (was 1,261 lines) — see docs/BACKLOG.md.
"""

from __future__ import annotations

import json
from pathlib import Path


from .constants import (
    CREATIVE_APPROVED_REPAIR_MANIFEST_PATH,
    CREATIVE_APPROVED_REPAIR_RECORDS_PATH,
    CREATIVE_REPAIR_RECORDS_PATH,
    CREATIVE_REPAIR_REVIEW_PATH,
)

from .storage import (
    _display_path,
    _load,
    _safe_int,
    now,
)


def _repair_training_record(item: dict, run: dict) -> dict:
    ranking = run.get("source_ranking") if isinstance(run.get("source_ranking"), dict) else {}
    sources = run.get("sources") if isinstance(run.get("sources"), list) else []
    source_labels = [str(source.get("label") or "") for source in sources if isinstance(source, dict)]
    top_source = sources[0] if sources and isinstance(sources[0], dict) else {}
    eval_passed = run.get("eval_passed") is True
    repair_note_in_top_three = ranking.get("repair_note_in_top_three") is True
    if eval_passed and repair_note_in_top_three:
        label = "good_repair"
    elif eval_passed:
        label = "needs_rerank"
    else:
        label = "needs_repair"
    return {
        "schema": "kenn.creative_repair_record.v1",
        "record_id": f"{item.get('id', '')}:{run.get('created_at', '')}",
        "created_at": now(),
        "feedback_id": item.get("id", ""),
        "question": item.get("question", ""),
        "rating": item.get("rating", ""),
        "target": item.get("target", ""),
        "comment": item.get("comment", ""),
        "original_answer": item.get("answer", ""),
        "repair_note": item.get("repair_note", ""),
        "eval_case_id": item.get("eval_case_id", ""),
        "main_eval_case_id": item.get("main_eval_case_id", ""),
        "main_eval_promoted": bool(item.get("main_eval_promoted_at")),
        "run_created_at": run.get("created_at", ""),
        "build_ok": run.get("build_ok") is True,
        "eval_passed": eval_passed,
        "eval_failures": run.get("failures", []) if isinstance(run.get("failures"), list) else [],
        "repaired_answer": run.get("answer", ""),
        "confidence": run.get("confidence", ""),
        "source_quality": run.get("source_quality", ""),
        "sources": sources,
        "source_labels": source_labels,
        "top_source_label": top_source.get("label", ""),
        "top_source_kind": top_source.get("kind", ""),
        "repair_note_rank": ranking.get("repair_note_rank"),
        "repair_note_in_top_three": repair_note_in_top_three,
        "repair_note_found": ranking.get("repair_note_found") is True,
        "needs_rerank_training": eval_passed and not repair_note_in_top_three,
        "label": label,
    }


def repair_training_records(data: dict | None = None) -> list[dict]:
    data = data or _load()
    records = []
    for item in data.get("feedback", []):
        if item.get("rating") not in {"wrong_direction", "bad_source"}:
            continue
        history = item.get("repair_history") if isinstance(item.get("repair_history"), list) else []
        for run in history:
            if isinstance(run, dict):
                records.append(_repair_training_record(item, run))
    return records


def export_repair_training_records(path: Path | None = None) -> dict:
    target = path or CREATIVE_REPAIR_RECORDS_PATH
    records = repair_training_records()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    return {
        "ok": True,
        "count": len(records),
        "path": _display_path(target),
        "message": f"Exported {len(records)} Creative Lab repair training record(s).",
    }


def _read_repair_training_records(path: Path) -> tuple[list[dict], int]:
    records = []
    skipped = 0
    if not path.exists():
        return records, skipped
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if isinstance(row, dict):
            row["record_id"] = str(row.get("record_id") or f"{row.get('feedback_id', '')}:{row.get('run_created_at', '')}")
            records.append(row)
        else:
            skipped += 1
    return records, skipped


def _load_repair_reviews(path: Path | None = None) -> dict:
    target = path or CREATIVE_REPAIR_REVIEW_PATH
    if not target.exists():
        return {"version": 1, "reviews": {}}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "reviews": {}}
    reviews = data.get("reviews")
    if not isinstance(reviews, dict):
        reviews = {}
    return {"version": int(data.get("version", 1) or 1), "reviews": reviews}


def _save_repair_reviews(data: dict, path: Path | None = None) -> None:
    target = path or CREATIVE_REPAIR_REVIEW_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def review_repair_training_record(record_id: str, decision: str, note: str = "") -> dict:
    clean_id = str(record_id or "").strip()
    clean_decision = str(decision or "").strip().lower()
    if not clean_id:
        return {"ok": False, "error": "Missing repair training record id."}
    if clean_decision not in {"approved", "rejected", "needs_work"}:
        return {"ok": False, "error": "Decision must be approved, rejected, or needs_work."}
    reviews = _load_repair_reviews()
    review = {
        "record_id": clean_id,
        "decision": clean_decision,
        "note": str(note or "").strip()[:1000],
        "reviewed_at": now(),
    }
    reviews["reviews"][clean_id] = review
    _save_repair_reviews(reviews)
    return {"ok": True, "review": review, "message": f"Marked repair training record as {clean_decision}."}


def export_approved_repair_training_records(path: Path | None = None) -> dict:
    target = path or CREATIVE_APPROVED_REPAIR_RECORDS_PATH
    source_records, skipped = _read_repair_training_records(CREATIVE_REPAIR_RECORDS_PATH)
    reviews = _load_repair_reviews()
    approved = []
    for record in source_records:
        review = reviews["reviews"].get(record.get("record_id", ""))
        if not isinstance(review, dict) or review.get("decision") != "approved":
            continue
        approved_record = {**record, "review": review, "review_decision": "approved"}
        approved.append(approved_record)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for record in approved:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    manifest = _repair_dataset_manifest(
        raw_path=CREATIVE_REPAIR_RECORDS_PATH,
        reviews_path=CREATIVE_REPAIR_REVIEW_PATH,
        output_path=target,
        decision="approved",
        records=source_records,
        selected=approved,
        skipped=skipped,
        reviews=reviews["reviews"],
    )
    CREATIVE_APPROVED_REPAIR_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREATIVE_APPROVED_REPAIR_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "count": len(approved),
        "source_count": len(source_records),
        "skipped": skipped,
        "path": _display_path(target),
        "manifest_path": _display_path(CREATIVE_APPROVED_REPAIR_MANIFEST_PATH),
        "message": f"Exported {len(approved)} approved Creative Lab repair training record(s).",
    }


def _count_by(records: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _repair_dataset_manifest(
    *,
    raw_path: Path,
    reviews_path: Path,
    output_path: Path,
    decision: str,
    records: list[dict],
    selected: list[dict],
    skipped: int,
    reviews: dict,
) -> dict:
    review_counts: dict[str, int] = {}
    for record in records:
        review = reviews.get(record.get("record_id", "")) if isinstance(reviews, dict) else None
        review_decision = str(review.get("decision") if isinstance(review, dict) else "unreviewed")
        review_counts[review_decision] = review_counts.get(review_decision, 0) + 1
    return {
        "schema": "kenn.creative_repair_dataset_manifest.v1",
        "created_at": now(),
        "raw_path": _display_path(raw_path),
        "reviews_path": _display_path(reviews_path),
        "output_path": _display_path(output_path),
        "decision": decision,
        "raw_records": len(records),
        "selected_records": len(selected),
        "skipped_rows": skipped,
        "review_counts": review_counts,
        "label_counts": _count_by(records, "label"),
        "selected_label_counts": _count_by(selected, "label"),
    }


def approved_repair_manifest_snapshot(path: Path | None = None) -> dict:
    target = path or CREATIVE_APPROVED_REPAIR_MANIFEST_PATH
    if not target.exists():
        return {"exists": False, "path": _display_path(target), "manifest": {}}
    try:
        manifest = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"exists": True, "path": _display_path(target), "error": f"Invalid manifest JSON: {exc}", "manifest": {}}
    if not isinstance(manifest, dict):
        return {"exists": True, "path": _display_path(target), "error": "Manifest root is not an object.", "manifest": {}}
    return {"exists": True, "path": _display_path(target), "manifest": manifest}


def validate_approved_repair_training_export() -> dict:
    records, skipped = _read_repair_training_records(CREATIVE_APPROVED_REPAIR_RECORDS_PATH)
    manifest_snapshot = approved_repair_manifest_snapshot()
    manifest = manifest_snapshot.get("manifest") or {}
    errors = []
    if not CREATIVE_APPROVED_REPAIR_RECORDS_PATH.exists():
        errors.append(f"Approved export missing: {_display_path(CREATIVE_APPROVED_REPAIR_RECORDS_PATH)}")
    if not manifest_snapshot.get("exists"):
        errors.append(f"Approved manifest missing: {manifest_snapshot.get('path', _display_path(CREATIVE_APPROVED_REPAIR_MANIFEST_PATH))}")
    if manifest_snapshot.get("error"):
        errors.append(str(manifest_snapshot["error"]))
    if skipped:
        errors.append(f"Approved export has {skipped} skipped row(s).")
    if manifest and manifest.get("schema") != "kenn.creative_repair_dataset_manifest.v1":
        errors.append("Manifest schema is not kenn.creative_repair_dataset_manifest.v1.")
    if manifest and manifest.get("decision") != "approved":
        errors.append(f"Manifest decision is {manifest.get('decision')!r}, expected 'approved'.")
    if manifest and _safe_int(manifest.get("selected_records"), -1) != len(records):
        errors.append(f"Manifest selected_records={manifest.get('selected_records')} but approved export has {len(records)} row(s).")
    for record in records:
        if record.get("review_decision") != "approved":
            errors.append(f"Record {record.get('record_id', '<missing>')} is not marked approved.")
    return {
        "ok": True,
        "valid": not errors,
        "errors": errors,
        "record_count": len(records),
        "skipped": skipped,
        "path": _display_path(CREATIVE_APPROVED_REPAIR_RECORDS_PATH),
        "manifest_path": manifest_snapshot.get("path", _display_path(CREATIVE_APPROVED_REPAIR_MANIFEST_PATH)),
        "manifest": manifest,
        "message": "Approved repair training export is valid." if not errors else "Approved repair training export needs attention.",
    }


def repair_training_export_snapshot(limit: int = 25, path: Path | None = None) -> dict:
    target = path or CREATIVE_REPAIR_RECORDS_PATH
    clean_limit = max(1, min(100, int(limit or 25)))
    reviews = _load_repair_reviews()
    if not target.exists():
        return {
            "ok": True,
            "exists": False,
            "path": _display_path(target),
            "count": 0,
            "skipped": 0,
            "review_counts": {},
            "approved_manifest": approved_repair_manifest_snapshot(),
            "records": [],
        }
    records, skipped = _read_repair_training_records(target)
    for row in records:
        row["review"] = reviews["reviews"].get(row["record_id"], {})
    review_counts: dict[str, int] = {}
    for record in records:
        decision = str((record.get("review") or {}).get("decision") or "unreviewed")
        review_counts[decision] = review_counts.get(decision, 0) + 1
    return {
        "ok": True,
        "exists": True,
        "path": _display_path(target),
        "count": len(records),
        "skipped": skipped,
        "review_counts": review_counts,
        "approved_manifest": approved_repair_manifest_snapshot(),
        "records": list(reversed(records[-clean_limit:])),
    }
