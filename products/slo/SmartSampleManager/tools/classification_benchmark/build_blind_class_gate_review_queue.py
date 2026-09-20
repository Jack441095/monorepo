#!/usr/bin/env python3
"""Export a candidate-hidden class-gate review queue.

The source manifest contains model candidates and is intentionally unsuitable
for an unbiased owner decision.  This exporter removes candidate class,
confidence, similarity and candidate-bearing hints from the reviewer CSV while
retaining the path and a content hash needed to bind the eventual label back
to the exact audio file.  It never creates labels, changes audio, or promotes a
policy.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any


VERSION = "candidate_hidden_class_gate_review_queue_v1"
FIELDS = [
    "id",
    "path",
    "content_sha256",
    "review_prompt",
    "human_label",
    "reviewer",
    "note",
]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        if payload.get("record_type") != "slo_class_conditional_gate_validation_manifest":
            raise ValueError("manifest receipt has an unexpected record type")
        rows = payload.get("items")
    else:
        rows = payload
    if not isinstance(rows, list) or not rows:
        raise ValueError("validation manifest must contain a non-empty list")

    required = {"id", "path", "candidate_class", "candidate_confidence", "vendor"}
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or not required.issubset(row):
            raise ValueError("every manifest row must contain the candidate and identity fields")
        row_id = str(row["id"])
        path_value = os.path.abspath(os.fspath(row["path"]))
        if row_id in seen_ids:
            raise ValueError(f"duplicate manifest id: {row_id}")
        if path_value in seen_paths:
            raise ValueError(f"duplicate manifest path: {path_value}")
        if not os.path.isabs(path_value):
            raise ValueError("review paths must be absolute")
        if not os.path.isfile(path_value):
            raise ValueError(f"review audio file does not exist: {path_value}")
        if not str(row.get("vendor", "")).strip():
            raise ValueError(f"manifest row {row_id} is missing vendor")
        seen_ids.add(row_id)
        seen_paths.add(path_value)
        normalized.append({"id": row_id, "path": path_value})
    return normalized


def build_queue(manifest_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = _load_manifest(manifest_path)
    output_rows: list[dict[str, Any]] = []
    for row in rows:
        audio_path = Path(row["path"])
        output_rows.append({
            "id": row["id"],
            "path": row["path"],
            "content_sha256": _sha256_file(audio_path),
            "review_prompt": (
                "Listen to the audio and enter the best supported frozen class; "
                "use UNKNOWN/OOD when no class is defensible."
            ),
            "human_label": "",
            "reviewer": "",
            "note": "",
        })

    receipt = {
        "record_type": "slo_candidate_hidden_class_gate_review_queue",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_manifest": str(manifest_path.resolve()),
        "source_manifest_sha256": _sha256_file(manifest_path),
        "n_rows": len(output_rows),
        "safety": {
            "candidate_fields_hidden": True,
            "filename_semantics_visible": True,
            "fully_blind": False,
            "labels_created": False,
            "policy_promoted": False,
            "rename_actions": False,
            "source_audio_modified": False,
        },
    }
    return receipt, output_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--csv-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args()

    receipt, rows = build_queue(args.manifest)
    args.csv_out.parent.mkdir(parents=True, exist_ok=True)
    with args.csv_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    receipt["csv_out"] = str(args.csv_out.resolve())
    receipt["csv_sha256"] = _sha256_file(args.csv_out)
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n_rows": len(rows), "csv": str(args.csv_out), "receipt": str(args.receipt_out)}, indent=2))


if __name__ == "__main__":
    main()
