#!/usr/bin/env python3
"""Audit whether rename-plan rows are eligible for explicit approval.

This is a fail-closed report, not an approval command. It never changes the
plan's `approved` field and never mutates the filesystem.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any


VERSION = "rename_approval_gate_v1"


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


def _read_plan(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if not rows or rows[0].get("record_type") != "slo_rename_plan":
        raise ValueError("plan must begin with slo_rename_plan")
    if int(rows[0].get("n_files", -1)) != len(rows) - 1:
        raise ValueError("plan row count does not match header")
    return rows[0], rows[1:]


def audit(plan_path: Path, duplicate_guard_path: Path) -> dict[str, Any]:
    header, rows = _read_plan(plan_path)
    guard = json.loads(duplicate_guard_path.read_text(encoding="utf-8"))
    guard_by_path = {row["path"]: row for row in guard.get("rows", [])}
    root = os.path.abspath(header.get("source_root", "/"))
    qualified = set(header.get("qualified_classes", []))
    outcomes = []
    counts = Counter()
    for row in rows:
        action = row.get("decision", {}).get("action")
        if action not in {"auto_rename", "suggest"}:
            continue
        path = os.path.abspath(str(row.get("path", "")))
        destination = os.path.abspath(str(row.get("destination", ""))) if row.get("destination") else ""
        reasons: list[str] = []
        if action == "suggest":
            reasons.append("suggestion_requires_explicit_approval")
        label = row.get("full_taxonomy_class") or row.get("audio_class") or row.get("decision", {}).get("displayed_label", "")
        if action == "auto_rename" and label not in qualified:
            reasons.append("class_not_qualified_for_auto_action")
        if bool(row.get("approved")):
            reasons.append("approval_already_present_in_source_plan")
        try:
            if os.path.commonpath([root, path]) != root or (destination and os.path.commonpath([root, destination]) != root):
                reasons.append("path_outside_source_root")
        except ValueError:
            reasons.append("path_outside_source_root")
        if not os.path.isfile(path):
            reasons.append("source_missing")
        else:
            if row.get("signature") != _signature(path):
                reasons.append("source_signature_mismatch")
        if destination and os.path.lexists(destination) and os.path.abspath(destination) != path:
            reasons.append("destination_exists")
        guard_row = guard_by_path.get(path, {})
        if "exact_duplicate_alias" in guard_row.get("flags", []):
            reasons.append("exact_duplicate_alias")
        if "exact_duplicate_canonical" in guard_row.get("flags", []):
            reasons.append("exact_duplicate_canonical")
        if "acoustic_near_duplicate" in guard_row.get("flags", []):
            reasons.append("acoustic_near_duplicate")
        status = "ready_for_explicit_approval" if not reasons else "blocked"
        counts[status] += 1
        for reason in reasons:
            counts[reason] += 1
        outcomes.append({"path": path, "action": action, "label": label, "status": status, "reasons": reasons})
    duplicate_blocked = sum(
        any(reason in {"exact_duplicate_alias", "exact_duplicate_canonical", "acoustic_near_duplicate"}
            for reason in row["reasons"])
        for row in outcomes
    )
    suggestion_rows = sum(row["action"] == "suggest" for row in outcomes)
    suggestion_without_duplicate_flags = sum(
        row["action"] == "suggest" and not any(
            reason in {"exact_duplicate_alias", "exact_duplicate_canonical", "acoustic_near_duplicate"}
            for reason in row["reasons"]
        )
        for row in outcomes
    )
    return {
        "record_type": "slo_rename_approval_gate_audit",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_plan": str(plan_path.resolve()),
        "source_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "duplicate_guard": str(duplicate_guard_path.resolve()),
        "qualified_classes": sorted(qualified),
        "n_candidate_rows": len(outcomes),
        "counts": dict(counts),
        "qualification_summary": {
            "suggestion_rows": suggestion_rows,
            "duplicate_blocked_rows": duplicate_blocked,
            "suggestion_rows_without_duplicate_flags": suggestion_without_duplicate_flags,
            "ready_for_explicit_approval": int(counts.get("ready_for_explicit_approval", 0)),
        },
        "rows": outcomes,
        "safety": {
            "read_only": True,
            "plan_modified": False,
            "approval_granted": False,
            "source_audio_modified": False,
            "rename_actions": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--duplicate-guard", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.plan, args.duplicate_guard)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n_candidate_rows": result["n_candidate_rows"], "counts": result["counts"]}, indent=2))


if __name__ == "__main__":
    main()
