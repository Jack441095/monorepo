#!/usr/bin/env python3
"""Evaluate optional reference-index retrieval evidence on explicit labels."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


VERSION = "evaluate_label_free_retrieval_evidence_v1"


def _key(path: str, marker: str) -> str:
    value = str(path).replace("\\", "/")
    token = marker.replace("\\", "/").strip("/") + "/"
    return value.split(token, 1)[1] if token in value else value.lstrip("/")


def _wilson(hits: int, n: int, z: float = 1.959963984540054) -> float | None:
    if n <= 0:
        return None
    p = hits / n
    den = 1 + z * z / n
    return max(0.0, (p + z * z / (2 * n) - z * math.sqrt(
        (p * (1 - p) + z * z / (4 * n)) / n)) / den)


def _labels(path: Path, marker: str, column: str) -> tuple[dict[str, str], int, int]:
    groups: dict[str, list[str]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "path" not in (reader.fieldnames or []) or column not in (reader.fieldnames or []):
            raise ValueError(f"label CSV must contain path and {column}")
        for row in reader:
            groups[_key(row.get("path") or "", marker)].append((row.get(column) or "").strip())
    result: dict[str, str] = {}
    conflicts = duplicates = 0
    for key, values in groups.items():
        if len(set(values)) > 1:
            conflicts += 1
        else:
            result[key] = values[-1]
            duplicates += max(0, len(values) - 1)
    return result, conflicts, duplicates


def evaluate(receipt: Path, labels: Path, out: Path,
             marker: str = "sample_pack_testing", label_column: str = "label") -> dict[str, Any]:
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    if payload.get("record_type") != "slo_label_free_retrieval_evidence":
        raise ValueError("input is not retrieval evidence")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("source_audio_modified")):
        raise ValueError("retrieval evidence is not read-only")
    prediction = {_key(row["path"], marker): row for row in payload.get("rows", [])
                  if isinstance(row, dict) and isinstance(row.get("path"), str)}
    gold, conflicts, duplicates = _labels(labels, marker, label_column)
    pairs: list[dict[str, Any]] = []
    missing = overlap = 0
    for key, label in gold.items():
        row = prediction.get(key)
        if row is None:
            missing += 1
            continue
        overlap += 1
        pairs.append({"gold": label, "pred": row.get("retrieval_candidate_label"),
                      "status": row.get("status"),
                      "similarity": row.get("retrieval_similarity"),
                      "exact_overlap_excluded": bool(row.get("exact_filename_overlap_excluded"))})
    suggested = [row for row in pairs if row["status"] == "suggest" and row["pred"]]
    hits = sum(row["gold"] == row["pred"] for row in suggested)
    result = {
        "record_type": "slo_label_free_retrieval_ground_truth_eval",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_receipt": str(receipt.resolve()),
        "source_labels": str(labels.resolve()),
        "n_label_rows": len(gold),
        "n_path_overlap": overlap,
        "n_missing_prediction": missing,
        "n_ambiguous_label_keys": conflicts,
        "n_identical_duplicate_label_rows": duplicates,
        "n_evaluated": len(pairs),
        "n_exact_filename_overlaps_in_eval": sum(row["exact_overlap_excluded"] for row in pairs),
        "n_suggested": len(suggested),
        "n_suggested_correct": hits,
        "suggestion_coverage": round(len(suggested) / len(pairs), 6) if pairs else None,
        "suggestion_precision": round(hits / len(suggested), 6) if suggested else None,
        "suggestion_wilson_lower_95": round(_wilson(hits, len(suggested)), 6) if suggested else None,
        "calibration_kind": "explicit_human_csv_exact_label_intersection",
        "accuracy_claim": None,
        "auto_action_allowed": False,
        "limitations": [
            "reference taxonomy labels are supervised evidence, not label-free inference",
            "near-duplicate leakage may remain even when exact filenames are excluded",
            "this is a measured subset, not a universal accuracy claim",
        ],
        "safety": {
            "read_only": True,
            "ground_truth_read": True,
            "semantic_labels_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "human_approval_required": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--marker", default="sample_pack_testing")
    parser.add_argument("--label-column", default="label")
    args = parser.parse_args()
    result = evaluate(args.receipt, args.labels, args.out, args.marker, args.label_column)
    print(json.dumps({"out": str(args.out), "n_evaluated": result["n_evaluated"],
                      "n_suggested": result["n_suggested"],
                      "suggestion_precision": result["suggestion_precision"],
                      "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
