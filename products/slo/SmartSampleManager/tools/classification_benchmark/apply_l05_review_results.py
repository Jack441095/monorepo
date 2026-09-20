#!/usr/bin/env python3
"""Validate human SLO L-05 review results and emit annotations only.

This command is deliberately not a training-data publisher.  It verifies two
reviewer decisions, preserves disagreement/adjudication information, checks
source SHA/path identity against the declared manifest, and writes a separate
annotation file plus an intake receipt.  It never rewrites the source
manifest, copies audio, or changes production model state.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path


TAXONOMY_CLASSES = (
    "Kick", "Snare", "Hi-Hat", "Clap", "Percussion", "Bass One-Shot",
    "Bass Loop", "Synth", "Synth Loop", "Vocal Phrase", "Vocal Loop",
    "Impact", "Riser", "Foley", "FX", "Atmosphere", "Music Loop",
)
ALLOWED_LABELS = set(TAXONOMY_CLASSES) | {"UNKNOWN", "OOD"}
ALLOWED_REVIEW_STATUSES = {"REVIEWED", "ABSTAINED"}
ALLOWED_ADJUDICATION_STATUSES = {"AGREED", "RESOLVED"}


def _read_json(path: Path) -> list[dict]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise RuntimeError("manifest must contain a list of objects")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise RuntimeError(f"cannot read review results {path}: {exc}") from exc


def _norm(value: object) -> str:
    return os.path.normcase(os.path.normpath(str(value)))


def _manifest_index(manifest: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in manifest:
        digest = row.get("source_sha256") or row.get("sha256")
        if not digest:
            continue
        if str(digest).lower() in result:
            raise RuntimeError(f"manifest contains duplicate source SHA-256: {digest}")
        result[str(digest).lower()] = row
    return result


def _path_matches(result_row: dict[str, str], manifest_row: dict) -> bool:
    review_path = result_row.get("source_path", "")
    manifest_paths = {
        str(manifest_row.get(field))
        for field in ("source_path", "full_evidence_relpath", "local_relative_path", "relative_path")
        if manifest_row.get(field)
    }
    if not review_path or not manifest_paths:
        return False
    normalized_review = _norm(review_path)
    return any(
        normalized_review == _norm(path)
        or normalized_review.endswith(os.sep + _norm(path).lstrip(os.sep))
        for path in manifest_paths
    )


def _require_label(row: dict[str, str], field: str, errors: list[str]) -> str:
    label = (row.get(field) or "").strip()
    if label not in ALLOWED_LABELS:
        errors.append(f"{field} must be one of the frozen classes, UNKNOWN, or OOD")
    return label


def _validate_review_row(row: dict[str, str], index: int, manifest_index: dict[str, dict]) -> tuple[dict, str]:
    errors: list[str] = []
    review_id = (row.get("review_id") or "").strip()
    if not review_id:
        errors.append("review_id is required")
    source_sha = (row.get("source_sha256") or "").strip().lower()
    manifest_row = manifest_index.get(source_sha)
    if not manifest_row:
        errors.append("source_sha256 does not resolve to the declared manifest")
    elif not _path_matches(row, manifest_row):
        errors.append("source_path does not match the manifest row for source_sha256")

    final_labels = []
    for reviewer in ("reviewer_1", "reviewer_2"):
        reviewer_id = (row.get(f"{reviewer}_id") or "").strip()
        status = (row.get(f"{reviewer}_status") or "").strip().upper()
        label = _require_label(row, f"{reviewer}_label", errors)
        if not reviewer_id:
            errors.append(f"{reviewer}_id is required")
        if status not in ALLOWED_REVIEW_STATUSES:
            errors.append(f"{reviewer}_status must be REVIEWED or ABSTAINED")
        if label in {"UNKNOWN", "OOD"} and not (row.get(f"{reviewer}_ambiguity_reason") or "").strip():
            errors.append(f"{reviewer}_ambiguity_reason is required for {label}")
        if label:
            final_labels.append(label)

    adjudicated = (row.get("adjudicated_label") or "").strip()
    if adjudicated not in ALLOWED_LABELS:
        errors.append("adjudicated_label must be one of the frozen classes, UNKNOWN, or OOD")
    adjudication_status = (row.get("adjudication_status") or "").strip().upper()
    if adjudication_status not in ALLOWED_ADJUDICATION_STATUSES:
        errors.append("adjudication_status must be AGREED or RESOLVED")
    if len(final_labels) == 2 and final_labels[0] == final_labels[1]:
        if adjudicated != final_labels[0] or adjudication_status != "AGREED":
            errors.append("matching reviewer labels require the same adjudicated_label and AGREED status")
    elif len(final_labels) == 2 and final_labels[0] != final_labels[1]:
        if adjudication_status != "RESOLVED" or not adjudicated:
            errors.append("disagreeing reviewer labels require an adjudicated label and RESOLVED status")
    if errors:
        raise RuntimeError(f"review row {index + 1} invalid: {'; '.join(errors)}")

    annotation = dict(manifest_row)
    annotation.update({
        "review_id": review_id,
        "reviewed_subcategory": adjudicated,
        "reviewed_is_ood": adjudicated == "OOD",
        "review_status": "ADJUDICATED",
        "review_authority": "INDEPENDENT_BLIND_REVIEW",
        "reviewer_1_id": row["reviewer_1_id"].strip(),
        "reviewer_1_label": final_labels[0],
        "reviewer_2_id": row["reviewer_2_id"].strip(),
        "reviewer_2_label": final_labels[1],
        "adjudication_status": adjudication_status,
        "adjudication_notes": (row.get("adjudication_notes") or "").strip(),
    })
    return annotation, review_id


def _write_json(path: Path, value: object) -> None:
    if path.exists():
        raise RuntimeError(f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def apply_review_results(
    manifest_path: Path,
    results_path: Path,
    annotations_path: Path,
    receipt_path: Path,
) -> dict:
    manifest = _read_json(manifest_path)
    rows = _read_csv(results_path)
    index = _manifest_index(manifest)
    annotations = []
    review_ids = set()
    source_shas = set()
    for row_index, row in enumerate(rows):
        annotation, review_id = _validate_review_row(row, row_index, index)
        source_sha = str(annotation.get("source_sha256") or annotation.get("sha256")).lower()
        if review_id in review_ids:
            raise RuntimeError(f"duplicate review_id: {review_id}")
        if source_sha in source_shas:
            raise RuntimeError(f"duplicate reviewed source SHA-256: {source_sha}")
        review_ids.add(review_id)
        source_shas.add(source_sha)
        annotations.append(annotation)
    if not annotations:
        raise RuntimeError("review results contain no completed rows")

    receipt = {
        "schema_version": "slo-l05-review-intake-v1",
        "status": "REVIEWED_ANNOTATIONS_READY",
        "review_count": len(annotations),
        "source_manifest": str(manifest_path),
        "source_manifest_sha256": _sha256(manifest_path),
        "review_results": str(results_path),
        "review_results_sha256": _sha256(results_path),
        "review_ids": sorted(review_ids),
        "production_model_changed": False,
        "source_manifest_changed": False,
        "training_promotion": "NOT_PERFORMED",
        "qualification_status": "NOT_QUALIFIED",
    }
    _write_json(annotations_path, annotations)
    _write_json(receipt_path, receipt)
    return {
        "status": receipt["status"],
        "review_count": len(annotations),
        "annotations": str(annotations_path),
        "receipt": str(receipt_path),
        "production_model_changed": False,
        "source_manifest_changed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--review-results", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = apply_review_results(
            args.manifest, args.review_results, args.annotations, args.receipt
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
