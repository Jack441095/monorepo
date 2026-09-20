#!/usr/bin/env python3
"""Evaluate temporal label-free evidence against explicit verification labels.

The evaluator compares the receipt's file-level maximum-window candidate with
an independent score-sum aggregation across windows.  It reads labels only for
evaluation, never writes labels or mutates audio/metadata.
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


VERSION = "evaluate_label_free_segment_classifier_v1"


def _key(path: str, marker: str) -> str:
    value = str(path).replace("\\", "/")
    token = marker.replace("\\", "/").strip("/") + "/"
    return value.split(token, 1)[1] if token in value else value.lstrip("/")


def _wilson(hits: int, n: int, z: float = 1.959963984540054) -> float | None:
    if n <= 0:
        return None
    p = hits / n
    den = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    spread = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n)
    return max(0.0, (centre - spread) / den)


def _read_labels(path: Path, marker: str, column: str) -> tuple[dict[str, str], int, int]:
    groups: dict[str, list[str]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "path" not in (reader.fieldnames or []) or column not in (reader.fieldnames or []):
            raise ValueError(f"label CSV must contain path and {column}")
        for row in reader:
            raw = row.get("path") or ""
            if not raw:
                raise ValueError("label row has no path")
            groups[_key(raw, marker)].append((row.get(column) or "").strip())
    result: dict[str, str] = {}
    conflicts = duplicates = 0
    for key, values in groups.items():
        unique = set(values)
        if len(unique) > 1:
            conflicts += 1
            continue
        result[key] = values[-1]
        duplicates += max(0, len(values) - 1)
    return result, conflicts, duplicates


def _stats(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [pair for pair in pairs if pair.get("pred")]
    hits = sum(pair["gold"] == pair["pred"] for pair in usable)
    return {
        "n_evaluated": len(pairs),
        "n_predicted": len(usable),
        "n_correct": hits,
        "coverage": round(len(usable) / len(pairs), 6) if pairs else None,
        "precision": round(hits / len(usable), 6) if usable else None,
        "wilson_lower_95": round(_wilson(hits, len(usable)), 6) if usable else None,
    }


def _temporal_vote(segments: list[dict[str, Any]]) -> str | None:
    """Choose the score-sum winner among scored windows.

    Summing scores rewards labels supported across multiple windows while
    retaining abstention when no scored segment exists.  This is an evaluation
    heuristic, not a calibrated probability.
    """
    totals: dict[str, float] = defaultdict(float)
    for segment in segments:
        label = segment.get("suggestion")
        score = segment.get("score")
        if isinstance(label, str) and label and isinstance(score, (int, float)):
            totals[label] += float(score)
    return max(totals, key=totals.get) if totals else None


def _load_receipt(path: Path, marker: str) -> dict[str, dict[str, Any]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError("segment receipt is empty")
    header = json.loads(lines[0])
    if header.get("record_type") != "slo_label_free_segment_classifier_receipt":
        raise ValueError("input is not a segment classifier receipt")
    safety = header.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("source_audio_modified")):
        raise ValueError("segment receipt is not read-only")
    result: dict[str, dict[str, Any]] = {}
    for line in lines[1:]:
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("segment row has no path")
        if row.get("semantic_label") is not None:
            raise ValueError("segment receipt contains a semantic label")
        key = _key(row["path"], marker)
        if key in result:
            raise ValueError(f"duplicate prediction suffix: {key}")
        result[key] = row
    return result


def evaluate(receipt: Path, labels: Path, out: Path,
             marker: str = "sample_pack_testing", label_column: str = "label",
             supported_labels: set[str] | None = None) -> dict[str, Any]:
    prediction = _load_receipt(receipt, marker)
    gold, conflicts, duplicates = _read_labels(labels, marker, label_column)
    if supported_labels is None:
        supported_labels = {str(row.get("suggestion"))
                            for row in prediction.values()
                            for row in row.get("segments", [])
                            if row.get("suggestion")}
    strategies = {"file_top": [], "temporal_vote": []}
    n_overlap = n_missing = n_unsupported = 0
    for key, label in gold.items():
        row = prediction.get(key)
        if row is None:
            n_missing += 1
            continue
        n_overlap += 1
        if label not in supported_labels:
            n_unsupported += 1
            continue
        file_suggestions = row.get("file_suggestions") or []
        file_top = file_suggestions[0].get("label") if file_suggestions else None
        segments = row.get("segments") or []
        strategies["file_top"].append({"key": key, "gold": label, "pred": file_top})
        strategies["temporal_vote"].append({
            "key": key, "gold": label, "pred": _temporal_vote(segments),
        })
    result = {
        "record_type": "slo_label_free_segment_classifier_ground_truth_eval",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_receipt": str(receipt.resolve()),
        "source_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
        "source_labels": str(labels.resolve()),
        "source_labels_sha256": hashlib.sha256(labels.read_bytes()).hexdigest(),
        "label_path_marker": marker,
        "label_column": label_column,
        "n_label_rows": len(gold),
        "n_ambiguous_label_keys": conflicts,
        "n_identical_duplicate_label_rows": duplicates,
        "n_path_overlap": n_overlap,
        "n_missing_prediction": n_missing,
        "n_unsupported_taxonomy": n_unsupported,
        "supported_label_count": len(supported_labels),
        "strategies": {name: _stats(pairs) for name, pairs in strategies.items()},
        "calibration_kind": "explicit_human_csv_exact_label_intersection",
        "accuracy_claim": None,
        "auto_action_allowed": False,
        "limitations": [
            "only exact labels in the supplied supported label set are scored",
            "temporal_vote is an uncalibrated score-sum heuristic",
            "path identity is suffix-matched under the declared marker",
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
    print(json.dumps({"out": str(args.out), "n_overlap": result["n_path_overlap"],
                      "strategies": result["strategies"], "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
