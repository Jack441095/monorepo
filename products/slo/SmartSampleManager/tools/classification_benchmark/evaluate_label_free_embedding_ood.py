#!/usr/bin/env python3
"""Describe embedding novelty over an explicit verified-label overlap.

This evaluator measures distributional separation only; it does not claim that
novelty is an accuracy probability.  It reads labels for evaluation and never
modifies the OOD receipt or source audio.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


VERSION = "evaluate_label_free_embedding_ood_v1"


def _key(path: str, marker: str) -> str:
    value = str(path).replace("\\", "/")
    token = marker.replace("\\", "/").strip("/") + "/"
    return value.split(token, 1)[1] if token in value else value.lstrip("/")


def _read_labels(path: Path, marker: str) -> tuple[dict[str, str], int, int]:
    groups: dict[str, list[str]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "path" not in (reader.fieldnames or []) or "label" not in (reader.fieldnames or []):
            raise ValueError("labels must contain path and label")
        for row in reader:
            raw = (row.get("path") or "").strip()
            label = (row.get("label") or "").strip()
            if raw and label:
                groups[_key(raw, marker)].append(label)
    result: dict[str, str] = {}
    conflicts = duplicates = 0
    for key, labels in groups.items():
        unique = set(labels)
        if len(unique) > 1:
            conflicts += 1
            continue
        result[key] = labels[-1]
        duplicates += max(0, len(labels) - 1)
    return result, conflicts, duplicates


def _stats(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    scores = [float(row["novelty_score"]) for row in rows]
    return {
        "n": len(rows),
        "mean_novelty": round(sum(scores) / len(scores), 6) if scores else None,
        "median_novelty": round(sorted(scores)[len(scores) // 2], 6) if scores else None,
        "max_novelty": round(max(scores), 6) if scores else None,
        "n_above_review_threshold": sum(score >= threshold for score in scores),
        "fraction_above_review_threshold": round(
            sum(score >= threshold for score in scores) / len(scores), 6) if scores else None,
    }


def evaluate(ood: Path, labels: Path, out: Path,
             marker: str = "sample_pack_testing", threshold: float = 0.35) -> dict[str, Any]:
    payload = json.loads(ood.read_text(encoding="utf-8"))
    if payload.get("record_type") != "slo_label_free_embedding_ood_receipt":
        raise ValueError("input is not an embedding OOD receipt")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("auto_action_allowed")):
        raise ValueError("OOD receipt is not read-only")
    labels_by_key, conflicts, duplicates = _read_labels(labels, marker)
    rows_by_key = {_key(str(row["path"]), marker): row for row in payload.get("rows", [])
                   if isinstance(row, dict) and isinstance(row.get("path"), str)}
    overlap: list[dict[str, Any]] = []
    missing = 0
    for key, label in labels_by_key.items():
        row = rows_by_key.get(key)
        if row is None:
            missing += 1
            continue
        item = dict(row)
        item["gold_label"] = label
        overlap.append(item)
    by_decision: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in overlap:
        by_decision[str(row.get("fused_decision") or "unclassified")].append(row)
        by_label[str(row["gold_label"])].append(row)
    result = {
        "record_type": "slo_label_free_embedding_ood_ground_truth_eval",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_ood_receipt": str(ood.resolve()),
        "source_ood_receipt_sha256": hashlib.sha256(ood.read_bytes()).hexdigest(),
        "source_labels": str(labels.resolve()),
        "source_labels_sha256": hashlib.sha256(labels.read_bytes()).hexdigest(),
        "label_path_marker": marker,
        "novelty_review_threshold": threshold,
        "n_label_rows": len(labels_by_key),
        "n_ambiguous_label_keys": conflicts,
        "n_identical_duplicate_label_rows": duplicates,
        "n_overlap": len(overlap),
        "n_missing": missing,
        "overall": _stats(overlap, threshold),
        "by_fused_decision": {
            name: _stats(rows, threshold) for name, rows in sorted(by_decision.items())
        },
        "by_verified_label": {
            name: _stats(rows, threshold) for name, rows in sorted(by_label.items())
        },
        "calibration_kind": "distributional_novelty_overlap_description",
        "accuracy_claim": None,
        "auto_action_allowed": False,
        "safety": {
            "read_only": True,
            "ground_truth_read": True,
            "semantic_labels_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "auto_action_allowed": False,
            "human_approval_required": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ood", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--marker", default="sample_pack_testing")
    parser.add_argument("--threshold", type=float, default=0.35)
    args = parser.parse_args()
    result = evaluate(args.ood, args.labels, args.out, args.marker, args.threshold)
    print(json.dumps({"out": str(args.out), "n_overlap": result["n_overlap"],
                      "overall": result["overall"], "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
