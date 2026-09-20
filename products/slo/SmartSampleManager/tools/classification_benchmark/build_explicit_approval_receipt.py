#!/usr/bin/env python3
"""Build a fail-closed approval receipt from an owner-reviewed CSV.

The input CSV is the exported owner queue with three fields filled in:
``owner_decision`` (approve/reject/defer), ``owner_reviewer``, and an optional
``owner_note``.  The command verifies that model evidence and source identity
were not edited, then emits an independent approval-gate receipt.  It never
changes a plan or applies a rename.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any


VERSION = "explicit_approval_receipt_v1"
DECISIONS = {"", "approve", "reject", "defer"}
DUPLICATE_FLAGS = {
    "acoustic_near_duplicate",
    "exact_duplicate_canonical",
    "exact_duplicate_alias",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _signature(path: str) -> dict[str, Any]:
    st = os.stat(path)
    digest = hashlib.sha256()
    digest.update(str(st.st_size).encode())
    with open(path, "rb") as handle:
        digest.update(handle.read(65536))
        if st.st_size > 131072:
            handle.seek(-65536, os.SEEK_END)
            digest.update(handle.read(65536))
    return {"size": int(st.st_size), "mtime_ns": int(st.st_mtime_ns), "edge_sha256": digest.hexdigest()}


def _same_number(left: Any, right: Any) -> bool:
    try:
        return abs(float(left) - float(right)) <= 1e-6
    except (TypeError, ValueError):
        return str(left or "") == str(right or "")


def _read_plan(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    with path.open(encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    if not records or records[0].get("record_type") != "slo_rename_plan":
        raise ValueError("source plan is not an slo_rename_plan")
    header, rows = records[0], records[1:]
    if int(header.get("n_files", -1)) != len(rows):
        raise ValueError("source plan row count mismatch")
    by_path: dict[str, dict[str, Any]] = {}
    for row in rows:
        path_value = os.path.abspath(str(row.get("path", "")))
        if not path_value or path_value in by_path:
            raise ValueError(f"source plan has missing or duplicate path: {path_value}")
        by_path[path_value] = row
    return header, by_path


def _read_decisions(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"path", "destination", "predicted_class", "owner_decision", "owner_reviewer", "owner_note"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"decision CSV missing columns: {sorted(missing)}")
        rows: dict[str, dict[str, str]] = {}
        for row in reader:
            path_value = os.path.abspath(str(row.get("path", "")))
            if not path_value or path_value in rows:
                raise ValueError(f"decision CSV has missing or duplicate path: {path_value}")
            decision = str(row.get("owner_decision", "")).strip().lower()
            if decision not in DECISIONS:
                raise ValueError(f"unsupported owner_decision {decision!r} for {path_value}")
            row["path"] = path_value
            row["owner_decision"] = decision
            rows[path_value] = row
    return rows


def build_receipt(collection_path: Path, duplicate_guard_path: Path,
                  decisions_path: Path) -> dict[str, Any]:
    collection = json.loads(collection_path.read_text(encoding="utf-8"))
    if collection.get("record_type") != "slo_review_collections":
        raise ValueError("collection is not slo_review_collections")
    plan_path = Path(str(collection.get("source_plan", "")))
    header, plan_rows = _read_plan(plan_path)
    if collection.get("source_plan_sha256") != _sha256(plan_path):
        raise ValueError("collection source plan hash no longer matches")
    guard = json.loads(duplicate_guard_path.read_text(encoding="utf-8"))
    if guard.get("record_type") != "slo_rename_duplicate_guard_audit":
        raise ValueError("duplicate guard has wrong record type")
    if guard.get("source_plan_sha256") != _sha256(plan_path):
        raise ValueError("duplicate guard does not match collection source plan")
    guard_by_path = {os.path.abspath(str(row.get("path"))): row for row in guard.get("rows", [])}
    decisions = _read_decisions(decisions_path)
    suggestions = list(collection.get("collections", {}).get("suggest", []))
    suggestion_by_path = {os.path.abspath(str(row.get("path"))): row for row in suggestions}
    if set(decisions) != set(suggestion_by_path):
        missing = sorted(set(suggestion_by_path) - set(decisions))
        extra = sorted(set(decisions) - set(suggestion_by_path))
        raise ValueError(f"decision CSV does not exactly match suggestions; missing={missing[:3]} extra={extra[:3]}")

    outcomes = []
    counts = Counter()
    for path, item in sorted(suggestion_by_path.items()):
        decision_row = decisions[path]
        plan_row = plan_rows.get(path)
        guard_row = guard_by_path.get(path)
        reasons: list[str] = []
        if plan_row is None:
            reasons.append("source_plan_row_missing")
        if guard_row is None:
            reasons.append("duplicate_guard_row_missing")
        if str(decision_row.get("destination", "")) != str(item.get("destination", "")):
            reasons.append("destination_changed")
        if str(decision_row.get("predicted_class", "")) != str(item.get("predicted_class", "")):
            reasons.append("predicted_class_changed")
        if str(decision_row.get("filename_class", "")) != str(item.get("filename_class", "")):
            reasons.append("filename_class_changed")
        if not _same_number(decision_row.get("confidence"), item.get("confidence")):
            reasons.append("confidence_changed")
        if not _same_number(decision_row.get("similarity"), item.get("similarity")):
            reasons.append("similarity_changed")
        expected_flags = ";".join(sorted(str(value) for value in (guard_row or {}).get("flags", [])))
        if str(decision_row.get("duplicate_flags", "")) != expected_flags:
            reasons.append("duplicate_flags_changed")
        owner_decision = decision_row["owner_decision"]
        reviewer = str(decision_row.get("owner_reviewer", "")).strip()
        if owner_decision == "":
            reasons.append("owner_decision_missing")
        elif owner_decision == "approve":
            if not reviewer:
                reasons.append("owner_reviewer_missing")
            if guard_row and set(guard_row.get("flags", [])) & DUPLICATE_FLAGS:
                reasons.extend(sorted(set(guard_row.get("flags", [])) & DUPLICATE_FLAGS))
            if plan_row is not None and (not os.path.isfile(path) or plan_row.get("signature") != _signature(path)):
                reasons.append("source_signature_mismatch")
        else:
            reasons.append(f"owner_{owner_decision}")
        status = "ready_for_explicit_approval" if owner_decision == "approve" and not reasons else "blocked"
        counts[status] += 1
        for reason in reasons:
            counts[reason] += 1
        outcomes.append({
            "path": path,
            "action": "suggest",
            "label": item.get("predicted_class", ""),
            "status": status,
            "reasons": reasons,
            "owner_decision": owner_decision,
            "owner_reviewer": reviewer,
            "owner_note": str(decision_row.get("owner_note", "")).strip(),
        })

    n_ready = int(counts.get("ready_for_explicit_approval", 0))
    counts.setdefault("ready_for_explicit_approval", 0)
    counts.setdefault("blocked", 0)
    return {
        "record_type": "slo_rename_approval_gate_audit",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_plan": str(plan_path.resolve()),
        "source_plan_sha256": _sha256(plan_path),
        "duplicate_guard": str(duplicate_guard_path.resolve()),
        "duplicate_guard_sha256": _sha256(duplicate_guard_path),
        "source_owner_review_queue": str(decisions_path.resolve()),
        "source_owner_review_queue_sha256": _sha256(decisions_path),
        "qualified_classes": [],
        "n_candidate_rows": len(outcomes),
        "counts": dict(counts),
        "qualification_summary": {
            "suggestion_rows": len(outcomes),
            "duplicate_blocked_rows": sum(any(r in DUPLICATE_FLAGS for r in row["reasons"]) for row in outcomes),
            "ready_for_explicit_approval": n_ready,
        },
        "rows": outcomes,
        "safety": {
            "read_only": True,
            "plan_modified": False,
            "approval_granted": bool(n_ready),
            "source_audio_modified": False,
            "rename_actions": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, required=True)
    parser.add_argument("--duplicate-guard", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = build_receipt(args.collection, args.duplicate_guard, args.decisions)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n_candidate_rows": receipt["n_candidate_rows"], "counts": receipt["counts"], "out": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
