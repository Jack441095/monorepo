#!/usr/bin/env python3
"""Import labels from a strict blind review bundle, fail-closed.

The reviewer CSV contains staged paths and blank ``human_label`` fields.  The
evaluator mapping contains the original paths and model candidates.  This
command joins them by ID, verifies staged/source content hashes, and emits the
existing evaluator-compatible labels CSV.  It never changes source audio,
production policy, or rename plans.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


VERSION = "strict_blind_class_gate_label_import_v1"
REVIEW_FIELDS = {
    "id", "review_path", "content_sha256", "review_prompt",
    "human_label", "reviewer", "note",
}
MAPPING_REQUIRED_FIELDS = {"id", "staged_path", "source_path", "content_sha256"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REVIEW_FIELDS.issubset(reader.fieldnames):
            raise ValueError("review CSV is missing strict-blind fields")
        return list(reader)


def _read_mapping(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("evaluator mapping root must be a JSON object")
    if payload.get("record_type") != "slo_strict_blind_class_gate_evaluator_mapping":
        raise ValueError("evaluator mapping has an unexpected record type")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("evaluator mapping must contain a non-empty rows list")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"evaluator mapping row {index} must be a JSON object")
        missing = sorted(MAPPING_REQUIRED_FIELDS - set(row))
        if missing:
            raise ValueError(
                f"evaluator mapping row {index} is missing required fields: {missing}"
            )
    return rows


def build_labels(review_csv: Path, mapping_path: Path, reviewer: str,
                 allow_incomplete: bool = False) -> tuple[list[dict[str, str]], dict[str, Any]]:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer must be non-empty")
    review_rows = _read_csv(review_csv)
    mapping_rows = _read_mapping(mapping_path)

    review_by_id: dict[str, dict[str, str]] = {}
    for row in review_rows:
        ident = str(row.get("id", "")).strip()
        if not ident or ident in review_by_id:
            raise ValueError(f"review CSV has missing or duplicate id: {ident}")
        review_path = Path(str(row.get("review_path", "")))
        if not review_path.is_absolute() or not review_path.is_file():
            raise ValueError(f"review staged path does not exist: {review_path}")
        expected_hash = str(row.get("content_sha256", "")).strip().lower()
        if len(expected_hash) != 64 or _sha256(review_path) != expected_hash:
            raise ValueError(f"staged content hash mismatch for id {ident}")
        entered_reviewer = str(row.get("reviewer", "")).strip()
        if entered_reviewer and entered_reviewer != reviewer:
            raise ValueError(f"reviewer mismatch for id {ident}")
        label = str(row.get("human_label", "")).strip()
        if not label or label == "__skip__":
            if not allow_incomplete:
                raise ValueError(f"id {ident} has no usable human_label")
        review_by_id[ident] = row

    mapping_by_id: dict[str, dict[str, Any]] = {}
    for row in mapping_rows:
        ident = str(row.get("id", "")).strip()
        if not ident or ident in mapping_by_id:
            raise ValueError(f"evaluator mapping has missing or duplicate id: {ident}")
        staged = Path(str(row.get("staged_path", "")))
        source = Path(str(row.get("source_path", "")))
        if ident not in review_by_id:
            raise ValueError(f"review CSV is missing mapping id: {ident}")
        if str(staged.resolve()) != str(Path(review_by_id[ident]["review_path"]).resolve()):
            raise ValueError(f"staged path mismatch for id {ident}")
        if not source.is_absolute() or not source.is_file():
            raise ValueError(f"source path does not exist for id {ident}: {source}")
        content_hash = str(row.get("content_sha256", "")).strip().lower()
        if _sha256(source) != content_hash:
            raise ValueError(f"source content hash mismatch for id {ident}")
        if content_hash != str(review_by_id[ident]["content_sha256"]).strip().lower():
            raise ValueError(f"source/review hash mismatch for id {ident}")
        mapping_by_id[ident] = row

    extras = sorted(set(review_by_id) - set(mapping_by_id))
    if extras:
        raise ValueError(f"review CSV has ids absent from evaluator mapping: {extras[:5]}")

    labels: list[dict[str, str]] = []
    for row in mapping_rows:
        ident = str(row["id"])
        review = review_by_id[ident]
        label = str(review.get("human_label", "")).strip()
        labels.append({
            "id": ident,
            "label": label,
            "path": str(Path(row["source_path"]).resolve()),
            "note": str(review.get("note", "")).strip(),
        })

    counts: dict[str, int] = {}
    for row in labels:
        counts[row["label"]] = counts.get(row["label"], 0) + 1
    receipt = {
        "record_type": "slo_strict_blind_class_gate_label_import",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_review_csv": str(review_csv.resolve()),
        "source_review_csv_sha256": _sha256(review_csv),
        "source_evaluator_mapping": str(mapping_path.resolve()),
        "source_evaluator_mapping_sha256": _sha256(mapping_path),
        "n_rows": len(labels),
        "n_usable_labels": sum(bool(row["label"]) and row["label"] != "__skip__" for row in labels),
        "label_counts": counts,
        "reviewer": reviewer,
        "allow_incomplete": bool(allow_incomplete),
        "safety": {
            "content_hashes_verified": True,
            "labels_created": False,
            "production_model_changed": False,
            "policy_promoted": False,
            "rename_actions": False,
            "source_audio_modified": False,
        },
    }
    return labels, receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-csv", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--labels-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    labels, receipt = build_labels(args.review_csv, args.mapping, args.reviewer, args.allow_incomplete)
    args.labels_out.parent.mkdir(parents=True, exist_ok=True)
    with args.labels_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "label", "path", "note"])
        writer.writeheader()
        writer.writerows(labels)
    receipt["labels_out"] = str(args.labels_out.resolve())
    receipt["labels_out_sha256"] = _sha256(args.labels_out)
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(labels), "usable_labels": receipt["n_usable_labels"], "labels_out": str(args.labels_out)}, indent=2))


if __name__ == "__main__":
    main()
