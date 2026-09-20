#!/usr/bin/env python3
"""Import completed taxonomy-gap decisions into a research manifest.

The queue is intentionally not self-labeling: every row must contain an owner
label, reviewer and note, and the label must be one of the options shown for
that row (or ``UNKNOWN``).  Hashes are checked against the source audio before
any decision is emitted.  The result is research evidence only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "id", "path", "content_sha256", "observed_label", "candidate_parent_options",
    "collection", "pack", "sample_family_id", "label_source", "owner_label",
    "owner_note", "owner_reviewer", "decision_status",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_decisions(queue_csv: Path, allow_incomplete: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with queue_csv.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_FIELDS.issubset(reader.fieldnames):
            raise ValueError("adjudication queue is missing required fields")
        rows = list(reader)

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    output: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        ident = row.get("id", "").strip()
        path = Path(row.get("path", "")).expanduser()
        if not ident or ident in seen_ids:
            raise ValueError(f"queue has missing or duplicate id: {ident}")
        if not path.is_absolute() or not path.is_file():
            raise ValueError(f"queue source path does not exist: {path}")
        resolved = str(path.resolve())
        if resolved in seen_paths:
            raise ValueError(f"queue has duplicate path: {resolved}")
        seen_ids.add(ident); seen_paths.add(resolved)
        expected_hash = row.get("content_sha256", "").strip().lower()
        if len(expected_hash) != 64 or sha256_file(path) != expected_hash:
            raise ValueError(f"content hash mismatch for queue id {ident}")

        owner_label = row.get("owner_label", "").strip()
        reviewer = row.get("owner_reviewer", "").strip()
        note = row.get("owner_note", "").strip()
        status = row.get("decision_status", "").strip().lower()
        options = {option.strip() for option in row.get("candidate_parent_options", "").split("|") if option.strip()}
        if not owner_label or status in {"", "pending"}:
            if not allow_incomplete:
                raise ValueError(f"queue id {ident} has no completed owner decision")
            skipped += 1
            continue
        if status not in {"approved", "adjudicated", "complete"}:
            raise ValueError(f"queue id {ident} has invalid decision_status: {status}")
        if not reviewer:
            raise ValueError(f"queue id {ident} is missing owner_reviewer")
        if not note:
            raise ValueError(f"queue id {ident} is missing owner_note")
        normalized_label = "OOD" if owner_label.upper() in {"OOD", "UNKNOWN"} else owner_label
        if owner_label.upper() not in {"OOD", "UNKNOWN"} and owner_label not in options:
            raise ValueError(f"owner label {owner_label!r} is not an offered option for queue id {ident}")

        output.append({
            "sample_id": ident,
            "path": resolved,
            "filename": path.name,
            "sha256": expected_hash,
            "vendor_id": row.get("collection", "").strip(),
            "vendor_id_source": "ground_truth.collection_proxy",
            "pack_id": row.get("pack", "").strip(),
            "source_family": row.get("sample_family_id", "").strip(),
            "expected_subcategory": normalized_label,
            "ood": normalized_label == "OOD",
            "ood_reason": note if normalized_label == "OOD" else "",
            "label_authority": "OWNER_ADJUDICATION",
            "label_source": row.get("label_source", "").strip(),
            "review_status": "adjudicated",
            "reviewer_id": reviewer,
            "review_note": note,
        })

    receipt = {
        "record_type": "slo_taxonomy_gap_adjudication_import",
        "schema_version": "1.0.0",
        "source_queue": str(queue_csv.resolve()),
        "source_queue_sha256": sha256_file(queue_csv),
        "queue_rows": len(rows),
        "imported_rows": len(output),
        "skipped_incomplete_rows": skipped,
        "known_rows": sum(not row["ood"] for row in output),
        "ood_rows": sum(row["ood"] for row in output),
        "policy": {
            "owner_decision_required": True,
            "hashes_verified": True,
            "labels_invented": False,
            "production_model_changed": False,
            "production_policy_changed": False,
        },
    }
    return output, receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args(argv)
    rows, receipt = import_decisions(args.queue, args.allow_incomplete)
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_out.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    receipt["manifest_out"] = str(args.manifest_out.resolve())
    receipt["manifest_out_sha256"] = sha256_file(args.manifest_out)
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"imported_rows": len(rows), "skipped": receipt["skipped_incomplete_rows"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
