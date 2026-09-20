#!/usr/bin/env python3
"""Read-only preflight for the leakage-controlled research inputs.

This checks cache schema, embedding shape, manifest identity/coverage and the
metadata required by the research scorecard *before* fitting a model.  It is
deliberately not an evaluator: it never creates labels, changes thresholds or
rewrites the SQLite cache.  A non-ready result is still useful evidence and is
reported with actionable missing fields/counts.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Keep direct execution and importlib-based tests independent of the caller's
# working directory.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import run_research_v3 as research


EXPECTED_CLASSES = {
    "Kick", "Snare", "Hi-Hat", "Clap", "Percussion", "Bass One-Shot",
    "Bass Loop", "Synth", "Synth Loop", "Vocal Phrase", "Vocal Loop",
    "Impact", "Riser", "Foley", "FX", "Atmosphere", "Music Loop",
}


def _path_identity_matches(cache_path: str, item: dict[str, Any]) -> bool:
    normalized_cache = os.path.normpath(os.path.abspath(cache_path))
    for field in research.MANIFEST_PATH_FIELDS:
        value = item.get(field)
        if not value:
            continue
        normalized_value = os.path.normpath(str(value))
        if normalized_cache == normalized_value or normalized_cache.endswith(
            os.sep + normalized_value.lstrip(os.sep)
        ):
            return True
    return False


def load_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("manifest must be a non-empty JSON list")
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise ValueError(f"manifest row {index} must be a JSON object")
        missing = sorted({"filename", "expected_subcategory"} - set(row))
        if missing:
            raise ValueError(f"manifest row {index} is missing required fields: {missing}")
    return payload


def _manifest_metadata(manifest: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize declared metadata, independent of cache coverage."""
    known = [row for row in manifest
             if row.get("expected_subcategory") != "OOD" and row.get("ood") is not True]
    ood = [row for row in manifest
           if row.get("expected_subcategory") == "OOD" or row.get("ood") is True]
    labels = [str(row.get("expected_subcategory", "")) for row in known]
    vendors = [str(row.get("vendor_id", "")) for row in known]
    ood_vendors = [str(row.get("vendor_id", "")) for row in ood]
    families = [str(row.get("source_family", "")) for row in known]
    errors: list[str] = []
    if known:
        try:
            research.validate_research_metadata(
                labels, families, vendors, ood_vendors, EXPECTED_CLASSES
            )
        except RuntimeError as exc:
            errors.append(str(exc).removeprefix("Cannot run L-05 research qualification: "))
    return {
        "known_rows": len(known),
        "ood_rows": len(ood),
        "known_class_counts": dict(Counter(labels)),
        "known_vendor_count": len(set(vendors)),
        "ood_vendor_count": len(set(ood_vendors)),
        "source_family_count": len(set(families) - {""}),
        "metadata_errors": errors,
    }


def preflight(manifest_path: Path, db_path: Path) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    declared_metadata = _manifest_metadata(manifest)
    lookup = research.build_manifest_lookup(manifest)
    hash_lookup = research.build_manifest_hash_lookup(manifest)

    cache_rows = 0
    usable_embeddings = 0
    matched_ids: set[int] = set()
    matched_by_hash = 0
    known_labels: list[str] = []
    known_vendors: list[str] = []
    known_families: list[str] = []
    ood_vendors: list[str] = []
    failures: Counter[str] = Counter()

    with sqlite3.connect(db_path) as conn:
        research.validate_cache_schema(conn, str(db_path))
        rows = conn.execute(
            "SELECT path, embedding FROM sample_cache "
            "WHERE embedding_status = 1 OR embedding_status IS NULL"
        ).fetchall()

    cache_rows = len(rows)
    for db_path_value, blob in rows:
        if not blob:
            failures["missing_embedding"] += 1
            continue
        try:
            research.decode_cache_embedding(blob, str(db_path_value))
        except RuntimeError as exc:
            failures[str(exc).split(": ", 1)[0]] += 1
            continue
        usable_embeddings += 1
        item = research.find_manifest_item(
            str(db_path_value),
            lookup,
            reject_ambiguous_basename=False,
            allow_basename_fallback=False,
            content_hash_lookup=hash_lookup,
        )
        if item is None:
            failures["unmatched_cache_row"] += 1
            continue
        matched_ids.add(id(item))
        path_matches = _path_identity_matches(str(db_path_value), item)
        hash_rows = hash_lookup.get(str(item.get("sha256", "")).lower(), [])
        if not path_matches and len(hash_rows) == 1 and hash_rows[0] is item:
            matched_by_hash += 1
        if item.get("expected_subcategory") == "OOD" or item.get("ood") is True:
            ood_vendors.append(str(item.get("vendor_id", "")))
        else:
            known_labels.append(str(item.get("expected_subcategory", "")))
            known_vendors.append(str(item.get("vendor_id", "")))
            known_families.append(str(item.get("source_family", "")))

    missing = [item for item in manifest if id(item) not in matched_ids]
    metadata_errors: list[str] = []
    if known_labels:
        try:
            research.validate_research_metadata(
                known_labels,
                known_families,
                known_vendors,
                ood_vendors,
                EXPECTED_CLASSES,
            )
        except RuntimeError as exc:
            metadata_errors.append(str(exc).removeprefix("Cannot run L-05 research qualification: "))
    else:
        metadata_errors.append("no matched known samples")

    ready = not missing and not failures and not metadata_errors and bool(ood_vendors)
    return {
        "record_type": "slo_research_input_preflight",
        "schema_version": "1.0.0",
        "manifest": str(manifest_path.resolve()),
        "cache": str(db_path.resolve()),
        "declared_manifest_rows": len(manifest),
        "cache_rows": cache_rows,
        "usable_embeddings": usable_embeddings,
        "matched_manifest_rows": len(matched_ids),
        "matched_by_content_hash": matched_by_hash,
        "missing_manifest_rows": len(missing),
        "missing_examples": [
            item.get("filename") or item.get("local_relative_path")
            for item in missing[:10]
        ],
        "known_rows": len(known_labels),
        "ood_rows": len(ood_vendors),
        "known_class_counts": dict(Counter(known_labels)),
        "known_vendor_count": len(set(known_vendors)),
        "ood_vendor_count": len(set(ood_vendors)),
        "source_family_count": len(set(known_families) - {""}),
        "declared_metadata": declared_metadata,
        "failures": dict(failures),
        "metadata_errors": metadata_errors,
        "ready_for_research_runner": ready,
        "safety": {
            "read_only": True,
            "labels_created": False,
            "cache_modified": False,
            "production_policy_changed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path)
    args = parser.parse_args(argv)
    receipt = preflight(args.manifest, args.db)
    if args.receipt_out:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["ready_for_research_runner"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
