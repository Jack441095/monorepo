#!/usr/bin/env python3
"""Measure a label-free specialist against an explicitly supplied label CSV.

This is an evaluation-only command.  It never treats filename/folder text as a
label, never modifies the receipt or audio, and reports only the defensible
intersection where the human CSV label exactly matches a specialist-bank
label.  Unsupported taxonomy rows are retained in coverage counts rather than
silently mapped.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


VERSION = "evaluate_label_free_specialist_v1"


def _key(path: str, marker: str) -> str:
    value = str(path).replace("\\", "/")
    marker = marker.replace("\\", "/").strip("/") + "/"
    if marker in value:
        return value.split(marker, 1)[1]
    return value.lstrip("/")


def _read_receipt(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError("specialist receipt is empty")
    header = json.loads(lines[0])
    if header.get("record_type") not in {"slo_label_free_specialist_receipt",
                                         "slo_label_free_specialist_ensemble_receipt"}:
        raise ValueError("input is not a specialist receipt")
    safety = header.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions")):
        raise ValueError("specialist receipt is not read-only")
    rows: dict[str, dict[str, Any]] = {}
    for line in lines[1:]:
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("specialist row has no path")
        if row.get("semantic_label") is not None:
            raise ValueError("specialist receipt contains a semantic label")
        if row["path"] in rows:
            raise ValueError(f"duplicate specialist path: {row['path']}")
        rows[row["path"]] = row
    return header, rows


def _labels(header: dict[str, Any]) -> set[str]:
    banks = header.get("specialist_prompt_banks") or {}
    result: set[str] = set()
    for bank in banks.values():
        if isinstance(bank, dict):
            result.update(str(label) for label in bank)
    return result


def _labels_for_domain(header: dict[str, Any], domain: str) -> set[str]:
    bank = (header.get("specialist_prompt_banks") or {}).get(domain) or {}
    return {str(label) for label in bank} if isinstance(bank, dict) else set()


def _wilson_lower(hits: int, n: int, z: float = 1.959963984540054) -> float | None:
    if n <= 0:
        return None
    p = hits / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    spread = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n)
    return max(0.0, (centre - spread) / denom)


def _read_labels(path: Path, marker: str, label_column: str) -> tuple[dict[str, dict[str, str]], int, int]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "path" not in (reader.fieldnames or []) or label_column not in (reader.fieldnames or []):
            raise ValueError(f"label CSV must contain path and {label_column}")
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in reader:
            raw_path = row.get("path") or ""
            if not raw_path:
                raise ValueError("label row has no path")
            key = _key(raw_path, marker)
            grouped[key].append({"label": (row.get(label_column) or "").strip(),
                                 "path": raw_path})
        rows: dict[str, dict[str, str]] = {}
        ambiguous = 0
        identical_duplicates = 0
        for key, values in grouped.items():
            labels = {value["label"] for value in values}
            if len(labels) > 1:
                # Conflicting adjudications cannot be resolved without making
                # a label choice, so exclude the key and report it explicitly.
                ambiguous += 1
                continue
            rows[key] = values[-1]
            identical_duplicates += max(0, len(values) - 1)
        return rows, ambiguous, identical_duplicates


def _stats(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(pairs)
    hits = sum(row["gold"] == row["pred"] for row in pairs)
    suggestions = [row for row in pairs if row["status"] == "suggest"]
    suggestion_hits = sum(row["gold"] == row["pred"] for row in suggestions)
    lower = _wilson_lower(hits, n)
    suggestion_lower = _wilson_lower(suggestion_hits, len(suggestions))
    return {
        "n_evaluated": n,
        "n_correct": hits,
        "accuracy": round(hits / n, 6) if n else None,
        "wilson_lower_95": round(lower, 6) if lower is not None else None,
        "n_suggested": len(suggestions),
        "n_suggested_correct": suggestion_hits,
        "suggestion_coverage": round(len(suggestions) / n, 6) if n else None,
        "suggestion_precision": round(suggestion_hits / len(suggestions), 6) if suggestions else None,
        "suggestion_wilson_lower_95": round(suggestion_lower, 6) if suggestion_lower is not None else None,
    }


def _sweep(pairs: list[dict[str, Any]], score_thresholds: tuple[float, ...],
           margin_thresholds: tuple[float, ...]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for score_threshold in score_thresholds:
        for margin_threshold in margin_thresholds:
            selected = [row for row in pairs
                        if row["score"] >= score_threshold and row["margin"] >= margin_threshold]
            stats = _stats([{**row, "status": "suggest"} for row in selected])
            points.append({
                "score_threshold": score_threshold,
                "margin_threshold": margin_threshold,
                "n_selected": stats["n_evaluated"],
                "precision": stats["accuracy"],
                "wilson_lower_95": stats["wilson_lower_95"],
            })
    return points


def evaluate(receipt: Path, labels: Path, out: Path,
             marker: str = "sample_pack_testing", label_column: str = "label") -> dict[str, Any]:
    header, prediction_rows = _read_receipt(receipt)
    label_rows, n_ambiguous_labels, n_identical_duplicate_labels = _read_labels(
        labels, marker, label_column)
    prediction_by_key: dict[str, dict[str, Any]] = {}
    for path, row in prediction_rows.items():
        key = _key(path, marker)
        if key in prediction_by_key:
            raise ValueError(f"ambiguous receipt suffix path: {key}")
        prediction_by_key[key] = row
    bank_labels = _labels(header)
    pairs: list[dict[str, Any]] = []
    n_overlap = 0
    n_unsupported = 0
    n_wrong_domain = 0
    n_missing_prediction = 0
    for key, label_row in label_rows.items():
        row = prediction_by_key.get(key)
        if row is None:
            n_missing_prediction += 1
            continue
        n_overlap += 1
        gold = label_row["label"]
        if gold not in bank_labels:
            n_unsupported += 1
            continue
        domain = str(row.get("domain_suggestion") or "unknown_or_mixture")
        domain_supported = gold in set((_labels_for_domain(header, domain)))
        if not domain_supported:
            n_wrong_domain += 1
        if row.get("specialist_status") != "scored":
            continue
        pairs.append({
            "key": key,
            "gold": gold,
            "pred": str(row.get("specialist_suggestion") or ""),
            "status": str(row.get("status") or "review"),
            "score": float(row.get("specialist_score"))
                if isinstance(row.get("specialist_score"), (int, float)) else float("-inf"),
            "margin": float(row.get("margin"))
                if isinstance(row.get("margin"), (int, float)) else float("-inf"),
            "domain_supported": domain_supported,
        })

    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        row = prediction_by_key[pair["key"]]
        by_domain[str(row.get("domain_suggestion") or "unknown_or_mixture")].append(
            pair)
    operating_points = _sweep(
        pairs,
        score_thresholds=(0.15, 0.20, 0.25, 0.30, 0.35),
        margin_thresholds=(0.03, 0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20),
    )
    viable_points = [point for point in operating_points
                     if point["n_selected"] >= 20 and point["wilson_lower_95"] is not None]
    best_lower_bound = max(viable_points,
                           key=lambda point: (point["wilson_lower_95"], point["n_selected"]),
                           default=None)
    domain_consistent_pairs = [row for row in pairs if row["domain_supported"]]
    domain_consistent_by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in domain_consistent_pairs:
        domain_consistent_by_domain[str(prediction_by_key[pair["key"]].get(
            "domain_suggestion") or "unknown_or_mixture")].append(pair)
    result = {
        "record_type": "slo_label_free_specialist_ground_truth_eval",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_receipt": str(receipt.resolve()),
        "source_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
        "source_labels": str(labels.resolve()),
        "source_labels_sha256": hashlib.sha256(labels.read_bytes()).hexdigest(),
        "label_path_marker": marker,
        "label_column": label_column,
        "n_label_rows": len(label_rows),
        "n_ambiguous_label_keys": n_ambiguous_labels,
        "n_identical_duplicate_label_rows": n_identical_duplicate_labels,
        "n_path_overlap": n_overlap,
        "n_missing_prediction": n_missing_prediction,
        "n_unsupported_taxonomy": n_unsupported,
        "n_wrong_domain_supported_labels": n_wrong_domain,
        "n_evaluated": len(pairs),
        "n_domain_consistent_evaluated": len(domain_consistent_pairs),
        "bank_label_count": len(bank_labels),
        "overall": _stats(pairs),
        "domains": {domain: _stats(rows) for domain, rows in sorted(by_domain.items())},
        "domain_consistent_overall": _stats(domain_consistent_pairs),
        "domain_consistent_domains": {
            domain: _stats(rows) for domain, rows in sorted(domain_consistent_by_domain.items())
        },
        "label_distribution": dict(sorted(Counter(row["gold"] for row in pairs).items())),
        "operating_points": operating_points,
        "best_measured_lower_bound_point": best_lower_bound,
        "calibration_kind": "explicit_human_csv_exact_label_intersection",
        "limitations": [
            "only labels exactly represented in the specialist prompt bank are evaluated",
            "path identity is suffix-matched under the declared marker",
            "this is a measured subset, not a universal accuracy claim",
        ],
        "accuracy_claim": None,
        "auto_action_allowed": False,
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
