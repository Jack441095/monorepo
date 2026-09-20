#!/usr/bin/env python3
"""Validate and export SLO's append-only C++ correction log.

The C++ engine writes a small JSONL record before applying a taxonomy override.
This command is the explicit bridge from that local evidence to a reviewable
packet. It never promotes labels, changes the training corpus, decodes audio,
or mutates source files. Existing output files are never overwritten.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any


METHOD_VERSION = "cpp_correction_log_ingest_v1"
CORRECTION_TYPES = {
    "label_correction",
    "not_in_list",
    "not_enough_info",
    "taxonomy_gap",
}
NOTE_REQUIRED = {"not_in_list", "not_enough_info", "taxonomy_gap"}
CSV_FIELDS = (
    "correction_id",
    "line_number",
    "created_at",
    "file_path",
    "path_exists",
    "content_hash",
    "original_category",
    "original_subcategory",
    "original_evidence",
    "original_confidence",
    "corrected_category",
    "corrected_subcategory",
    "correction_type",
    "user_note",
    "taxonomy_version",
    "classifier_version",
    "policy_version",
    "review_status",
)


def _text(row: dict[str, Any], key: str, *, required: bool = False) -> str:
    value = row.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{key} must be non-empty")
    return value


def _absolute_normalized(value: str, key: str) -> str:
    if not os.path.isabs(value):
        raise ValueError(f"{key} must be absolute")
    normalized = os.path.normpath(value)
    if normalized != value:
        raise ValueError(f"{key} must be normalized")
    return value


def _correction_id(raw_line: str) -> str:
    return "corr-" + hashlib.sha256(raw_line.encode("utf-8")).hexdigest()[:24]


def normalize_record(raw: dict[str, Any], *, line_number: int, raw_line: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("record must be an object")
    file_path = _absolute_normalized(_text(raw, "file_path", required=True), "file_path")
    correction_type = _text(raw, "correction_type") or "label_correction"
    if correction_type not in CORRECTION_TYPES:
        raise ValueError(f"unsupported correction_type: {correction_type}")
    note = _text(raw, "user_note")
    if correction_type in NOTE_REQUIRED and not note:
        raise ValueError(f"{correction_type} requires user_note")

    confidence = raw.get("original_confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError) as exc:
        raise ValueError("original_confidence must be numeric") from exc
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("original_confidence must be in [0, 1]")

    status = _text(raw, "status") or "pending"
    if status != "pending":
        raise ValueError("C++ correction records must enter as pending")

    content_hash = _text(raw, "content_hash")
    if content_hash and (len(content_hash) != 64 or any(c not in "0123456789abcdefABCDEF" for c in content_hash)):
        raise ValueError("content_hash must be a SHA-256 hex string when present")

    return {
        "correction_id": _correction_id(raw_line),
        "line_number": line_number,
        "created_at": _text(raw, "ts") or _text(raw, "created_at", required=True),
        "file_path": file_path,
        "path_exists": Path(file_path).is_file(),
        "content_hash": content_hash,
        "original_category": _text(raw, "original_category"),
        "original_subcategory": _text(raw, "original_subcategory"),
        "original_evidence": _text(raw, "original_evidence"),
        "original_confidence": confidence,
        "corrected_category": _text(raw, "corrected_category"),
        "corrected_subcategory": _text(raw, "corrected_subcategory"),
        "correction_type": correction_type,
        "user_note": note,
        "taxonomy_version": _text(raw, "taxonomy_version"),
        "classifier_version": _text(raw, "classifier_version"),
        "policy_version": _text(raw, "policy_version") or "1.0.0",
        "review_status": "pending",
    }


def read_log(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"correction log does not exist: {path}")
    rows: list[dict[str, Any]] = []
    ids: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            if not raw_line.strip():
                continue
            try:
                raw = json.loads(raw_line)
                row = normalize_record(raw, line_number=line_number, raw_line=raw_line.rstrip("\n"))
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"invalid correction record at {path}:{line_number}: {exc}") from exc
            if row["correction_id"] in ids:
                raise ValueError(f"duplicate correction record at {path}:{line_number}")
            ids.add(row["correction_id"])
            rows.append(row)
    if not rows:
        raise ValueError("correction log is empty")
    return rows


def _write_new(path: Path, writer) -> None:
    if path.exists():
        raise ValueError(f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    writer(path)


def export_packet(rows: list[dict[str, Any]], output_dir: Path, source_log: Path) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    packet_csv = output_dir / "pending_corrections_review.csv"
    packet_json = output_dir / "pending_corrections_review.json"

    def write_csv(path: Path) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    counts = Counter(row["correction_type"] for row in rows)
    missing = sum(not row["path_exists"] for row in rows)
    payload = {
        "record_type": "slo_cpp_correction_review_packet",
        "schema_version": "1.0.0",
        "method_version": METHOD_VERSION,
        "created_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_log": str(source_log.resolve()),
        "summary": {
            "pending_count": len(rows),
            "correction_type_counts": dict(sorted(counts.items())),
            "paths_missing": missing,
        },
        "safety": {
            "read_only": True,
            "audio_decoded": False,
            "audio_modified": False,
            "training_ground_truth_changed": False,
            "rename_actions": False,
            "automatic_promotion": False,
        },
        "decision": "OWNER_REVIEW_REQUIRED",
        "rows": rows,
    }

    _write_new(packet_csv, write_csv)
    _write_new(packet_json, lambda path: path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8"))
    return {
        "status": "READY_FOR_OWNER_REVIEW",
        "packet_csv": str(packet_csv),
        "packet_json": str(packet_json),
        "pending_count": len(rows),
        "paths_missing": missing,
        "automatic_promotion": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        rows = read_log(args.log)
        result = export_packet(rows, args.output_dir, args.log)
    except ValueError as exc:
        print(f"FAIL CLOSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
