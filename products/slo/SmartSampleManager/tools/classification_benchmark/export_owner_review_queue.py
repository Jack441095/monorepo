#!/usr/bin/env python3
"""Export an evidence-backed, read-only owner review queue.

This flattens the immutable review collection into a sortable CSV.  It never
promotes suggestions, creates labels, or applies filesystem actions.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


VERSION = "owner_review_queue_v1"
FIELDS = [
    "review_rank",
    "path",
    "destination",
    "predicted_class",
    "filename_class",
    "confidence",
    "similarity",
    "nearest_reference_label",
    "nearest_reference_path",
    "aspect_overall",
    "duration_seconds",
    "form_hint",
    "form_hint_confidence",
    "spectral_centroid_hz",
    "low_band_energy_ratio",
    "high_band_energy_ratio",
    "periodicity_strength",
    "duplicate_flags",
    "reason",
    "requires_approval",
    "owner_decision",
    "owner_reviewer",
    "owner_note",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _load(path: Path, record_type: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("record_type") != record_type:
        raise ValueError(f"{path} is not {record_type}")
    return payload


def build_queue(collection_path: Path, guard_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    collection = _load(collection_path, "slo_review_collections")
    guard = _load(guard_path, "slo_rename_duplicate_guard_audit")
    guard_rows = {str(row.get("path")): row for row in guard.get("rows", [])}
    suggestions = list(collection.get("collections", {}).get("suggest", []))
    rows: list[dict[str, Any]] = []
    for item in suggestions:
        path = str(item.get("path", ""))
        if not path or path not in guard_rows:
            raise ValueError(f"suggestion has no matching duplicate-guard row: {path}")
        evidence = item.get("review_evidence") or {}
        reference = evidence.get("nearest_labelled_reference") or {}
        aspects = evidence.get("aspect_similarity_to_reference") or {}
        facets = evidence.get("facets") or {}
        flags = sorted(str(value) for value in (guard_rows[path].get("flags") or []))
        rows.append({
            "path": path,
            "destination": str(item.get("destination", "")),
            "predicted_class": str(item.get("predicted_class", "")),
            "filename_class": str(item.get("filename_class", "")),
            "confidence": _number(item.get("confidence")),
            "similarity": _number(item.get("similarity")),
            "nearest_reference_label": str(reference.get("label", "")),
            "nearest_reference_path": str(reference.get("path", "")),
            "aspect_overall": _number(aspects.get("overall")),
            "duration_seconds": _number(facets.get("duration_seconds")),
            "form_hint": str(facets.get("form_hint", "")),
            "form_hint_confidence": _number(facets.get("form_hint_confidence")),
            "spectral_centroid_hz": _number(facets.get("spectral_centroid_hz")),
            "low_band_energy_ratio": _number(facets.get("low_band_energy_ratio")),
            "high_band_energy_ratio": _number(facets.get("high_band_energy_ratio")),
            "periodicity_strength": _number(facets.get("periodicity_strength")),
            "duplicate_flags": ";".join(flags),
            "reason": str(item.get("reason", "")),
            "requires_approval": bool(item.get("requires_approval", True)),
            "owner_decision": "",
            "owner_reviewer": "",
            "owner_note": "",
        })

    # Put duplicate-flagged and lower-similarity rows first.  This is only a
    # review ordering; it cannot change the model decision or action policy.
    rows.sort(key=lambda row: (
        0 if row["duplicate_flags"] else 1,
        row["similarity"] if row["similarity"] is not None else 1.0,
        row["confidence"] if row["confidence"] is not None else 1.0,
        row["path"],
    ))
    for rank, row in enumerate(rows, start=1):
        row["review_rank"] = rank
    return {
        "record_type": "slo_owner_review_queue",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_collection": str(collection_path.resolve()),
        "source_collection_sha256": _sha256(collection_path),
        "source_duplicate_guard": str(guard_path.resolve()),
        "source_duplicate_guard_sha256": _sha256(guard_path),
        "n_rows": len(rows),
        "safety": {
            "read_only": True,
            "labels_created": False,
            "suggestions_promoted": False,
            "rename_actions": False,
            "source_audio_modified": False,
        },
    }, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, required=True)
    parser.add_argument("--duplicate-guard", type=Path, required=True)
    parser.add_argument("--csv-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args()
    receipt, rows = build_queue(args.collection, args.duplicate_guard)
    with args.csv_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    receipt["csv_out"] = str(args.csv_out.resolve())
    receipt["csv_sha256"] = _sha256(args.csv_out)
    args.receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n_rows": receipt["n_rows"], "csv": str(args.csv_out), "receipt": str(args.receipt_out)}, indent=2))


if __name__ == "__main__":
    main()
