#!/usr/bin/env python3
"""Fail-closed validator for the SLO L-05 classification evidence package.

This checks metadata and result files only.  It never decodes, hashes, copies,
or modifies audio, and it cannot manufacture a human-review receipt.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path


TAXONOMY_CLASSES = (
    "Kick", "Snare", "Hi-Hat", "Clap", "Percussion", "Bass One-Shot",
    "Bass Loop", "Synth", "Synth Loop", "Vocal Phrase", "Vocal Loop",
    "Impact", "Riser", "Foley", "FX", "Atmosphere", "Music Loop",
)
ARTIFACT_CLASS_ORDER = tuple(sorted(TAXONOMY_CLASSES))
REQUIRED_PER_CLASS_FIELDS = {
    "class", "support", "precision", "recall", "f1", "coverage",
    "abstention_rate", "mean_confidence", "accepted_count",
}
REQUIRED_ABSTENTION_FIELDS = {
    "threshold", "known_count", "accepted_known_count", "coverage",
    "abstention_count", "abstention_rate", "accepted_known_accuracy",
    "mean_known_confidence", "ood_count", "false_known_ood_count",
    "false_known_ood_rate",
}
WEAK_CLASSES_REQUIRING_EXPLICIT_DECISION = {"Atmosphere", "Vocal Loop"}
ALLOWED_CLASS_DECISION_STATUSES = {"qualified", "exploratory", "suppressed"}


def _read_json(path: Path, errors: list[str]):
    if not path.is_file():
        errors.append(f"missing file: {path.name}")
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid JSON {path.name}: {exc}")
        return None


def _check_rate(value, field: str, errors: list[str]) -> None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        errors.append(f"{field} must be numeric")
        return
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
        errors.append(f"{field} must be finite and within [0, 1]")


def _validate_manifest(base_dir: Path, errors: list[str]) -> dict:
    manifest = _read_json(base_dir / "dataset_manifest.json", errors)
    if not isinstance(manifest, list):
        errors.append("dataset_manifest.json must contain a list")
        return {"known": [], "ood": [], "vendors": set(), "families": {}}

    known = [
        item for item in manifest
        if isinstance(item, dict)
        and not item.get("ood")
        and item.get("expected_subcategory") != "OOD"
    ]
    ood = [
        item for item in manifest
        if isinstance(item, dict)
        and (item.get("ood") or item.get("expected_subcategory") == "OOD")
    ]
    classes = {item.get("expected_subcategory") for item in known}
    if classes != set(TAXONOMY_CLASSES):
        errors.append(
            "manifest known classes do not equal frozen 17-class taxonomy: "
            f"missing={sorted(set(TAXONOMY_CLASSES) - classes)}, "
            f"unexpected={sorted(classes - set(TAXONOMY_CLASSES))}"
        )

    vendors = {item.get("vendor_id") for item in known if item.get("vendor_id")}
    if len(vendors) < 2:
        errors.append("known evaluation set must contain at least two vendors")
    ood_vendors = {item.get("vendor_id") for item in ood if item.get("vendor_id")}
    if not ood:
        errors.append("evaluation set must contain an OOD population")
    elif len(ood_vendors) < 2:
        errors.append("OOD evaluation set must contain at least two vendors")

    families_by_class = defaultdict(set)
    labels_by_family = defaultdict(set)
    for item in known:
        family = item.get("source_family")
        label = item.get("expected_subcategory")
        if not family:
            errors.append(f"known sample missing source_family: {item.get('filename')}")
            continue
        families_by_class[label].add(family)
        labels_by_family[family].add(label)

    insufficient = {
        label: len(families_by_class[label])
        for label in TAXONOMY_CLASSES
        if len(families_by_class[label]) < 5
    }
    if insufficient:
        errors.append(f"classes lack five source families: {insufficient}")

    mixed = {
        family: sorted(labels)
        for family, labels in labels_by_family.items()
        if len(labels) > 1
    }
    if mixed:
        errors.append(f"source families carry mixed known labels: {list(mixed)[:5]}")

    return {
        "known": known,
        "ood": ood,
        "vendors": vendors,
        "families_by_class": families_by_class,
        "mixed_families": mixed,
    }


def _validate_metrics(base_dir: Path, errors: list[str]) -> None:
    metrics = _read_json(base_dir / "metrics.json", errors)
    if not isinstance(metrics, dict):
        return
    required = {
        "evaluation_provenance", "group_key", "taxonomy_class_count", "coverage",
        "confidence_mean", "false_unknown_rate", "abstention_rate",
        "false_known_ood_rate",
    }
    missing = sorted(required - metrics.keys())
    if missing:
        errors.append(f"metrics.json missing L-05 fields: {missing}")
    if metrics.get("evaluation_provenance") != "out_of_fold_predictions":
        errors.append("metrics.json must declare out_of_fold_predictions")
    if metrics.get("group_key") != "source_family":
        errors.append("metrics.json must declare source_family as group_key")
    if metrics.get("taxonomy_class_count") != len(TAXONOMY_CLASSES):
        errors.append("metrics.json must declare exactly 17 taxonomy classes")
    for field in (
        "coverage", "confidence_mean", "false_unknown_rate",
        "abstention_rate", "false_known_ood_rate",
    ):
        if field in metrics:
            _check_rate(metrics[field], f"metrics.{field}", errors)


def _validate_per_class(base_dir: Path, errors: list[str]) -> None:
    path = base_dir / "per_class_metrics.csv"
    if not path.is_file():
        errors.append("missing file: per_class_metrics.csv")
        return
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    fields = set(rows[0]) if rows else set()
    missing = sorted(REQUIRED_PER_CLASS_FIELDS - fields)
    if missing:
        errors.append(f"per_class_metrics.csv missing L-05 fields: {missing}")
    classes = {row.get("class") for row in rows}
    if classes != set(TAXONOMY_CLASSES) or len(rows) != len(TAXONOMY_CLASSES):
        errors.append("per_class_metrics.csv must contain exactly one row for each of 17 classes")
    for index, row in enumerate(rows):
        for field in ("precision", "recall", "f1", "coverage", "abstention_rate", "mean_confidence"):
            if field in row:
                _check_rate(row[field], f"per_class_metrics row {index}.{field}", errors)


def _validate_confusion(base_dir: Path, errors: list[str]) -> None:
    path = base_dir / "confusion_matrix.csv"
    if not path.is_file():
        errors.append("missing file: confusion_matrix.csv")
        return
    with path.open(newline="") as handle:
        rows = list(csv.reader(handle))
    if len(rows) != len(TAXONOMY_CLASSES) + 1:
        errors.append("confusion_matrix.csv must contain a 17x17 matrix")
        return
    columns = rows[0][1:]
    row_labels = [row[0] for row in rows[1:] if row]
    if columns != list(ARTIFACT_CLASS_ORDER) or row_labels != list(ARTIFACT_CLASS_ORDER):
        errors.append("confusion_matrix.csv labels must match the frozen taxonomy order")
    if any(len(row) != len(TAXONOMY_CLASSES) + 1 for row in rows):
        errors.append("confusion_matrix.csv has inconsistent row widths")
    for row_index, row in enumerate(rows[1:], start=1):
        for column_index, value in enumerate(row[1:], start=1):
            try:
                numeric = float(value)
            except ValueError:
                errors.append(f"confusion_matrix cell {row_index},{column_index} is not numeric")
                continue
            if not math.isfinite(numeric) or numeric < 0 or not numeric.is_integer():
                errors.append(f"confusion_matrix cell {row_index},{column_index} is not a non-negative integer")


def _validate_ood_and_abstention(base_dir: Path, errors: list[str]) -> None:
    ood = _read_json(base_dir / "ood_results.json", errors)
    if not isinstance(ood, dict):
        ood = {}
    policy = ood.get("acceptance_policy")
    required_policy = {
        "threshold", "known_coverage", "known_false_unknown_rate",
        "ood_false_known_count", "ood_false_known_rate",
    }
    if not isinstance(policy, dict):
        errors.append("ood_results.json missing acceptance_policy")
    else:
        missing = sorted(required_policy - policy.keys())
        if missing:
            errors.append(f"ood_results.json acceptance_policy missing: {missing}")
        for field in ("known_coverage", "known_false_unknown_rate", "ood_false_known_rate"):
            if field in policy and policy[field] is not None:
                _check_rate(policy[field], f"ood.acceptance_policy.{field}", errors)

    abstention = _read_json(base_dir / "abstention_metrics.json", errors)
    if not isinstance(abstention, dict):
        return
    if abstention.get("evaluation_provenance") != "out_of_fold_predictions":
        errors.append("abstention_metrics.json must declare out_of_fold_predictions")
    thresholds = abstention.get("thresholds")
    if not isinstance(thresholds, list) or not thresholds:
        errors.append("abstention_metrics.json must contain a threshold sweep")
        return
    for index, row in enumerate(thresholds):
        if not isinstance(row, dict):
            errors.append(f"abstention threshold row {index} is not an object")
            continue
        missing = sorted(REQUIRED_ABSTENTION_FIELDS - row.keys())
        if missing:
            errors.append(f"abstention threshold row {index} missing: {missing}")


def _validate_review_receipt(base_dir: Path, review_receipt_name: str, errors: list[str]) -> None:
    receipt = _read_json(base_dir / review_receipt_name, errors)
    if not isinstance(receipt, dict):
        errors.append("independent blind-review receipt is required; owner_review_queue.csv is not sufficient")
        return
    required = {
        "schema_version", "status", "reviewers", "reviewed_at",
        "blind_protocol", "disagreement_handling", "owner_signoff",
    }
    missing = sorted(required - receipt.keys())
    if missing:
        errors.append(f"blind-review receipt missing: {missing}")
    if not isinstance(receipt.get("reviewers"), list) or not receipt.get("reviewers"):
        errors.append("blind-review receipt must list at least one reviewer")
    elif any(
        not isinstance(reviewer, dict)
        or not reviewer.get("id")
        or not reviewer.get("role")
        for reviewer in receipt["reviewers"]
    ):
        errors.append("each blind-reviewer entry must contain an id and role")
    if receipt.get("status") not in {"accepted", "approved"}:
        errors.append("blind-review receipt status must be accepted or approved")
    if receipt.get("owner_signoff") is not True:
        errors.append("blind-review receipt must contain explicit owner_signoff=true")
    for field in ("reviewed_at", "blind_protocol", "disagreement_handling"):
        if field in receipt and not receipt[field]:
            errors.append(f"blind-review receipt field must be non-empty: {field}")


def _validate_weak_class_decisions(base_dir: Path, errors: list[str]) -> None:
    """Require explicit product decisions for historically weak classes."""
    decisions = _read_json(base_dir / "weak_class_decisions.json", errors)
    if not isinstance(decisions, dict):
        errors.append("weak_class_decisions.json is required for Atmosphere and Vocal Loop")
        return

    if decisions.get("taxonomy_class_count") != len(TAXONOMY_CLASSES):
        errors.append("weak_class_decisions.json must declare exactly 17 taxonomy classes")

    rows = decisions.get("decisions")
    if not isinstance(rows, list):
        errors.append("weak_class_decisions.json must contain a decisions list")
        return

    by_class = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"weak class decision row {index} is not an object")
            continue
        label = row.get("class")
        if label in by_class:
            errors.append(f"weak class decision is duplicated: {label}")
        by_class[label] = row
        if label not in WEAK_CLASSES_REQUIRING_EXPLICIT_DECISION:
            continue
        for field in ("status", "rationale", "evidence_ref"):
            if not row.get(field):
                errors.append(f"weak class decision for {label} missing: {field}")
        if row.get("status") not in ALLOWED_CLASS_DECISION_STATUSES:
            errors.append(
                f"weak class decision for {label} has invalid status: {row.get('status')}"
            )

    missing = sorted(WEAK_CLASSES_REQUIRING_EXPLICIT_DECISION - by_class.keys())
    if missing:
        errors.append(f"weak class decisions missing explicit entries: {missing}")


def validate(base_dir: Path, review_receipt_name: str = "blind_review_receipt.json") -> dict:
    errors: list[str] = []
    manifest = _validate_manifest(base_dir, errors)
    _validate_metrics(base_dir, errors)
    _validate_per_class(base_dir, errors)
    _validate_confusion(base_dir, errors)
    _validate_ood_and_abstention(base_dir, errors)
    _validate_weak_class_decisions(base_dir, errors)
    _validate_review_receipt(base_dir, review_receipt_name, errors)
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "known_count": len(manifest["known"]),
        "ood_count": len(manifest["ood"]),
        "vendor_count": len(manifest["vendors"]),
        "taxonomy_class_count": len({
            item.get("expected_subcategory") for item in manifest["known"]
        }),
        "review_receipt": review_receipt_name,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, default=Path(__file__).parent)
    parser.add_argument("--review-receipt", default="blind_review_receipt.json")
    args = parser.parse_args()
    result = validate(args.base_dir, args.review_receipt)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
