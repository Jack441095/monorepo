#!/usr/bin/env python3
"""Consolidate taxonomy-gap queues without double-counting audio.

Queues can be generated from different reviewed sessions and therefore overlap
by content hash.  This merge keeps one deterministic row per hash, carries a
consistent owner decision if present, and blocks contradictory observed or
owner labels.  It never assigns a parent class and never modifies source audio.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


FIELDS = ["id", "path", "content_sha256", "observed_label", "candidate_parent_options",
          "collection", "pack", "sample_family_id", "label_source", "owner_label",
          "owner_note", "owner_reviewer", "decision_status"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def merge_queues(inputs: list[Path], output: Path) -> dict[str, Any]:
    observations: dict[str, list[dict[str, str]]] = defaultdict(list)
    input_receipts = []
    for source in inputs:
        with source.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not set(FIELDS[1:]).issubset(reader.fieldnames):
                raise ValueError(f"queue is missing required fields: {source}")
            rows = list(reader)
        input_receipts.append({"path": str(source.resolve()), "sha256": sha256_file(source), "rows": len(rows)})
        for index, row in enumerate(rows):
            content_hash = (row.get("content_sha256") or "").strip().lower()
            path = Path((row.get("path") or "").strip()).expanduser()
            if len(content_hash) != 64 or not path.is_absolute() or not path.is_file():
                raise ValueError(f"invalid queue row {source}:{index + 2}")
            if sha256_file(path) != content_hash:
                raise ValueError(f"queue hash mismatch: {source}:{index + 2}")
            value = {field: (row.get(field) or "").strip() for field in FIELDS}
            value["path"] = str(path.resolve()); value["content_sha256"] = content_hash
            observations[content_hash].append(value)

    conflicts = []
    merged: list[dict[str, str]] = []
    aliases = 0
    for content_hash in sorted(observations):
        values = observations[content_hash]
        observed = {row["observed_label"] for row in values}
        options = {row["candidate_parent_options"] for row in values}
        owner = {row["owner_label"] for row in values if row["owner_label"]}
        if len(observed) > 1 or len(options) > 1 or len(owner) > 1:
            conflicts.append({"content_sha256": content_hash,
                              "observed_labels": sorted(observed),
                              "candidate_options": sorted(options),
                              "owner_labels": sorted(owner),
                              "rows": values})
            continue
        values.sort(key=lambda row: (row["path"], row["label_source"], row["id"]))
        chosen = dict(values[0]); aliases += len(values) - 1
        # Preserve a completed decision over a pending duplicate, while still
        # requiring all completed copies to agree (checked above).
        completed = [row for row in values if row["owner_label"]]
        if completed:
            chosen.update({key: completed[0][key] for key in
                           ("owner_label", "owner_note", "owner_reviewer", "decision_status")})
        chosen["id"] = f"merged-{len(merged) + 1:04d}"
        merged.append(chosen)

    for row in merged:
        if row["owner_label"] and row["decision_status"].lower() in {"", "pending"}:
            raise ValueError(f"owner label has pending status for merged row {row['id']}")

    output = output.resolve()
    if output.exists():
        raise ValueError(f"refusing to overwrite existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(merged)
    return {
        "record_type": "slo_taxonomy_gap_queue_merge",
        "schema_version": "1.0.0",
        "inputs": input_receipts,
        "queue_out": str(output), "queue_out_sha256": sha256_file(output),
        "input_rows": sum(item["rows"] for item in input_receipts),
        "unique_content_hashes": len(observations), "merged_rows": len(merged),
        "duplicate_alias_rows_collapsed": aliases,
        "conflict_hashes_blocked": len(conflicts), "conflicts": conflicts,
        "owner_decided_rows_carried": sum(bool(row["owner_label"]) for row in merged),
        "policy": {"content_hash_deduplication": True, "conflicts_blocked": True,
                   "labels_created": False, "source_audio_modified": False,
                   "production_policy_changed": False, "owner_approval_required": True},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = merge_queues(args.input, args.out)
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"merged_rows": receipt["merged_rows"], "conflicts": receipt["conflict_hashes_blocked"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
