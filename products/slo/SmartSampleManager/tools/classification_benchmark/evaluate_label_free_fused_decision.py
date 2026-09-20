#!/usr/bin/env python3
"""Evaluate a fused open-world decision receipt against explicit labels.

Only exact labels represented by the supplied prediction label set are scored.
This is an evaluation artifact, never a training or rename operation.
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


VERSION = "evaluate_label_free_fused_decision_v1"


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
    suggestions = [pair for pair in pairs if pair["decision"] == "suggest"]
    hits = sum(pair["gold"] == pair["pred"] for pair in suggestions)
    return {
        "n_evaluated": len(pairs),
        "n_suggested": len(suggestions),
        "n_suggested_correct": hits,
        "suggestion_coverage": round(len(suggestions) / len(pairs), 6) if pairs else None,
        "suggestion_precision": round(hits / len(suggestions), 6) if suggestions else None,
        "suggestion_wilson_lower_95": round(_wilson(hits, len(suggestions)), 6)
            if suggestions else None,
    }


def _sweep(pairs: list[dict[str, Any]], thresholds: tuple[float, ...] =
           (0.0, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35)) -> list[dict[str, Any]]:
    points = []
    for threshold in thresholds:
        selected = [pair for pair in pairs
                    if pair["decision"] == "suggest"
                    and pair["confidence"] is not None
                    and pair["confidence"] >= threshold]
        hits = sum(pair["gold"] == pair["pred"] for pair in selected)
        points.append({
            "confidence_threshold": threshold,
            "n_selected": len(selected),
            "n_correct": hits,
            "precision": round(hits / len(selected), 6) if selected else None,
            "wilson_lower_95": round(_wilson(hits, len(selected)), 6)
                if selected else None,
        })
    return points


def evaluate(receipt: Path, labels: Path, out: Path,
             marker: str = "sample_pack_testing", label_column: str = "label",
             supported_labels: set[str] | None = None) -> dict[str, Any]:
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    if payload.get("record_type") not in {
            "slo_label_free_fused_decision_receipt",
            "slo_label_free_ood_gated_decision_receipt",
    }:
        raise ValueError("input is not a fused decision receipt")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("auto_action_allowed")):
        raise ValueError("fused receipt is not read-only")
    prediction: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows", []):
        key = _key(str(row.get("path", "")), marker)
        if not key:
            continue
        if key in prediction:
            raise ValueError(f"duplicate prediction suffix: {key}")
        prediction[key] = row
    gold, conflicts, duplicates = _read_labels(labels, marker, label_column)
    if supported_labels is None:
        supported_labels = {str(row.get("candidate_label")) for row in prediction.values()
                            if row.get("candidate_label")}
    pairs: list[dict[str, Any]] = []
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
        pairs.append({"key": key, "gold": label,
                      "pred": str(row.get("candidate_label") or ""),
                      "decision": str(row.get("decision") or "review"),
                      "domain": str(row.get("domain") or "unknown_or_mixture"),
                      "confidence": float(row["confidence_floor"])
                      if isinstance(row.get("confidence_floor"), (int, float)) else None})
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        by_domain[pair["domain"]].append(pair)
    operating_points = _sweep(pairs)
    viable = [point for point in operating_points
              if point["n_selected"] >= 20 and point["wilson_lower_95"] is not None]
    best = max(viable, key=lambda point: (point["wilson_lower_95"], point["n_selected"]),
               default=None)
    result = {
        "record_type": "slo_label_free_fused_decision_ground_truth_eval",
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
        "n_evaluated": len(pairs),
        "overall": _stats(pairs),
        "domains": {domain: _stats(rows) for domain, rows in sorted(by_domain.items())},
        "operating_points": operating_points,
        "best_measured_lower_bound_point": best,
        "decision_counts": {
            decision: sum(row.get("decision") == decision for row in payload.get("rows", []))
            for decision in ("suggest", "review", "unknown_domain")
        },
        "calibration_kind": "explicit_human_csv_exact_label_intersection",
        "accuracy_claim": None,
        "auto_action_allowed": False,
        "limitations": [
            "only exact labels in the supplied supported label set are scored",
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
    print(json.dumps({"out": str(args.out), "n_evaluated": result["n_evaluated"],
                      "overall": result["overall"], "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
