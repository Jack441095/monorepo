#!/usr/bin/env python3
"""Evaluate a completed SLO export at KENN's advisory adapter boundary.

Input is JSONL with one privacy-safe row per labelled evaluation case:
``{"case_id":"opaque", "project_bucket":"opaque", "expected_label":"kick",
"expected_ood_status":"in_distribution",
"classification": {<kenn.audio_classification.v1 completed payload>}}``.
No audio, paths, filenames, prompts, or model code are accepted.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))

SCHEMA = "kenn.slo_adapter_evaluation.v1"
OOD_STATUSES = frozenset({"in_distribution", "unknown", "out_of_distribution"})


def _text(value: Any, limit: int = 128) -> str:
    return str(value or "").strip()[:limit]


def evaluate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from kenn.core.audio_classification import AudioClassificationError, normalize

    errors: list[str] = []
    labels: list[str] = []
    audio_predictions: list[str] = []
    audio_confidences: list[float] = []
    metadata_predictions: list[str] = []
    ood_counts: Counter[str] = Counter()
    projects: set[str] = set()
    model_identities: set[tuple[str, str, str, str]] = set()
    selected_predictions: list[tuple[str, str]] = []
    latencies_ms: list[float] = []
    per_class: defaultdict[str, Counter[str]] = defaultdict(Counter)
    ood_expected_counts: Counter[str] = Counter()
    ood_rejected_correctly: Counter[str] = Counter()
    valid_case_count = 0
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"row {index}: must be an object")
            continue
        case_id = _text(row.get("case_id"))
        project_bucket = _text(row.get("project_bucket"))
        expected_ood_status = _text(row.get("expected_ood_status"), 32)
        expected = _text(row.get("expected_label"), 96)
        if not case_id or not project_bucket or expected_ood_status not in OOD_STATUSES:
            errors.append(f"row {index}: case_id, project_bucket, and expected_ood_status are required")
            continue
        if expected_ood_status == "in_distribution" and not expected:
            errors.append(f"row {index}: expected_label is required for in-distribution cases")
            continue
        try:
            classification = normalize(row.get("classification") or {})
        except AudioClassificationError as exc:
            errors.append(f"row {index}: invalid classification: {exc}")
            continue
        valid_case_count += 1
        projects.add(project_bucket)
        audio_prediction = _text((classification["audio_only"] or [{}])[0].get("label"), 96)
        metadata_prediction = _text((classification["metadata_assisted"] or [{}])[0].get("label"), 96)
        if expected_ood_status == "in_distribution":
            labels.append(expected)
            audio_predictions.append(audio_prediction)
            metadata_predictions.append(metadata_prediction)
            audio_confidences.append(float((classification["audio_only"] or [{}])[0].get("probability") or 0.0))
        model_identities.add((
            classification["model_id"], classification["model_sha256"],
            classification["label_map_sha256"], classification["inference_version"],
        ))
        if expected_ood_status == "in_distribution" and classification["selected_source"] != "unknown":
            selected_predictions.append((expected, classification["selected_label"]))
        if expected_ood_status != "in_distribution":
            ood_expected_counts[expected_ood_status] += 1
            if (classification["selected_source"] == "unknown"
                    and classification["out_of_distribution"]["status"] == expected_ood_status):
                ood_rejected_correctly[expected_ood_status] += 1
        latencies_ms.append(float(classification["latency_ms"]))
        if expected_ood_status == "in_distribution":
            per_class[expected]["support"] += 1
            per_class[expected]["audio_correct"] += int(audio_prediction == expected)
            per_class[expected]["metadata_correct"] += int(metadata_prediction == expected)
        ood_counts[classification["out_of_distribution"]["status"]] += 1

    def metrics(predictions: list[str]) -> dict[str, Any]:
        if not labels:
            return {"accuracy": None, "macro_f1": None, "per_class": {}}
        all_labels = sorted(set(labels) | set(predictions))
        f1s: list[float] = []
        detail: dict[str, Any] = {}
        for label in all_labels:
            tp = sum(expected == label and predicted == label for expected, predicted in zip(labels, predictions))
            fp = sum(expected != label and predicted == label for expected, predicted in zip(labels, predictions))
            fn = sum(expected == label and predicted != label for expected, predicted in zip(labels, predictions))
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            f1s.append(f1)
            detail[label] = {
                "support": sum(expected == label for expected in labels),
                "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            }
        return {
            "accuracy": round(sum(expected == predicted for expected, predicted in zip(labels, predictions)) / len(labels), 4),
            "macro_f1": round(sum(f1s) / len(f1s), 4),
            "per_class": detail,
        }

    def expected_calibration_error(predictions: list[str], confidences: list[float]) -> float | None:
        if not labels or len(labels) != len(predictions) or len(labels) != len(confidences):
            return None
        total = len(labels)
        error = 0.0
        for bucket in range(10):
            lower, upper = bucket / 10.0, (bucket + 1) / 10.0
            members = [index for index, confidence in enumerate(confidences)
                       if lower <= confidence < upper or (bucket == 9 and confidence == 1.0)]
            if not members:
                continue
            confidence_mean = sum(confidences[index] for index in members) / len(members)
            accuracy_mean = sum(labels[index] == predictions[index] for index in members) / len(members)
            error += (len(members) / total) * abs(accuracy_mean - confidence_mean)
        return round(error, 4)

    audio_only = metrics(audio_predictions)
    metadata_assisted = metrics(metadata_predictions)
    if len(model_identities) > 1:
        errors.append("evaluation rows contain more than one model, label map, or inference version")
    selected_correct = sum(expected == predicted for expected, predicted in selected_predictions)
    selected_accuracy = (selected_correct / len(selected_predictions)) if selected_predictions else None
    sorted_latencies = sorted(latencies_ms)
    p95_index = max(0, math.ceil(len(sorted_latencies) * 0.95) - 1) if sorted_latencies else None
    ood_evaluation = {
        status: {
            "case_count": ood_expected_counts[status],
            "correct_rejection_count": ood_rejected_correctly[status],
            "correct_rejection_rate": round(ood_rejected_correctly[status] / ood_expected_counts[status], 4)
            if ood_expected_counts[status] else None,
        }
        for status in ("unknown", "out_of_distribution")
    }
    return {
        "schema": SCHEMA,
        "status": "evaluated" if not errors and valid_case_count else "invalid",
        "case_count": valid_case_count,
        "project_bucket_count": len(projects),
        "audio_only": audio_only,
        "metadata_assisted": metadata_assisted,
        "calibration": {"audio_only_ece": expected_calibration_error(audio_predictions, audio_confidences), "bin_count": 10},
        "ood_status_counts": dict(sorted(ood_counts.items())),
        "ood_evaluation": ood_evaluation,
        "artifact_identity": (
            {
                "model_id": next(iter(model_identities))[0],
                "model_sha256": next(iter(model_identities))[1],
                "label_map_sha256": next(iter(model_identities))[2],
                "inference_version": next(iter(model_identities))[3],
            }
            if len(model_identities) == 1 else None
        ),
        "selective_prediction": {
            "accepted_case_count": len(selected_predictions),
            "abstained_case_count": len(labels) - len(selected_predictions),
            "accuracy": round(selected_accuracy, 4) if selected_accuracy is not None else None,
        },
        "latency_ms": {
            "mean": round(sum(latencies_ms) / len(latencies_ms), 3) if latencies_ms else None,
            "p95": round(sorted_latencies[p95_index], 3) if p95_index is not None else None,
        },
        "errors": errors,
        "promotion_eligible": False,
        "next_step": "Review class-specific calibration, Unknown/OOD behaviour, latency, and a fixed KENN usefulness benchmark before explicit advisory-only enablement.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True, help="Privacy-safe JSONL labelled cases.")
    args = parser.parse_args()
    rows = []
    try:
        for line_number, line in enumerate(args.cases.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip():
                rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "invalid", "error": str(exc), "promotion_eligible": False}, indent=2))
        return 2
    report = evaluate_rows(rows)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "evaluated" else 2


if __name__ == "__main__":
    raise SystemExit(main())
