#!/usr/bin/env python3
"""Select a deterministic, breadth-first batch from the taxonomy-gap queue."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict, Counter
from pathlib import Path


REQUIRED = {
    "id", "path", "content_sha256", "observed_label", "candidate_parent_options",
    "collection", "pack", "sample_family_id", "owner_label", "owner_note",
    "owner_reviewer", "decision_status",
}


def _stable(row: dict[str, str]) -> str:
    return hashlib.sha256(f"{row.get('content_sha256','')}|{row.get('id','')}".encode()).hexdigest()


def _excluded_hashes(paths: list[Path]) -> set[str]:
    excluded: set[str] = set()
    for path in paths:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "content_sha256" not in reader.fieldnames:
                raise ValueError(f"exclusion CSV is missing content_sha256: {path}")
            for row in reader:
                value = (row.get("content_sha256") or "").strip().lower()
                if value:
                    excluded.add(value)
    return excluded


def select_batch(queue_csv: Path, limit: int,
                 exclude_csvs: list[Path] | None = None) -> tuple[list[dict[str, str]], dict[str, object]]:
    if limit <= 0:
        raise ValueError("batch limit must be positive")
    with queue_csv.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames):
            raise ValueError("taxonomy-gap queue is missing required fields")
        rows = list(reader)

    # A completed row is never silently reissued. Pending rows are the only
    # rows eligible for a new batch; rows with an owner decision stay in the
    # source queue for the importer.
    excluded_hashes = _excluded_hashes(exclude_csvs or [])
    pending_before_exclusion = [row for row in rows if not row.get("owner_label", "").strip()
                                and row.get("decision_status", "").strip().lower() == "pending"]
    pending = [row for row in pending_before_exclusion
               if row.get("content_sha256", "").strip().lower() not in excluded_hashes]
    groups: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for row in pending:
        groups[row.get("candidate_parent_options", "")][row.get("collection", "")].append(row)
    for collections in groups.values():
        for values in collections.values():
            values.sort(key=_stable)

    selected: list[dict[str, str]] = []
    group_names = sorted(groups)
    target = min(limit, len(pending))
    # Guarantee a first representative from every option group whenever the
    # requested batch is large enough.  Without this pass, a group with many
    # collections could consume the whole batch before later groups are seen.
    offsets: dict[tuple[str, str], int] = {}
    for group_name in group_names:
        collections = groups[group_name]
        collection_names = sorted(collections)
        if len(selected) >= target:
            break
        collection = collection_names[0]
        values = collections[collection]
        selected.append(dict(values[0]))
        offsets[(group_name, collection)] = 1

    # Continue round-robin across option groups and then collections.  This
    # keeps the remainder of a batch balanced without sacrificing coverage.
    depth = 0
    while len(selected) < target:
        made_progress = False
        for group_name in group_names:
            collections = groups[group_name]
            for collection in sorted(collections):
                values = collections[collection]
                index = offsets.get((group_name, collection), 0)
                if index < len(values):
                    selected.append(dict(values[index]))
                    offsets[(group_name, collection)] = index + 1
                    made_progress = True
                    if len(selected) >= limit:
                        break
            if len(selected) >= limit:
                break
        if not made_progress:
            break
        depth += 1

    selected.sort(key=lambda row: (_stable(row), row.get("id", "")))
    for index, row in enumerate(selected, start=1):
        row["batch_row"] = str(index)
    receipt = {
        "record_type": "slo_taxonomy_gap_review_batch",
        "schema_version": "1.0.0",
        "source_queue": str(queue_csv.resolve()),
        "source_queue_sha256": hashlib.sha256(queue_csv.read_bytes()).hexdigest(),
        "source_rows": len(rows),
        "pending_source_rows": len(pending),
        "pending_before_exclusion": len(pending_before_exclusion),
        "excluded_batch_files": [str(path.resolve()) for path in (exclude_csvs or [])],
        "excluded_content_hashes": len(excluded_hashes),
        "excluded_pending_rows": len(pending_before_exclusion) - len(pending),
        "selected_rows": len(selected),
        "option_group_counts": dict(Counter(row.get("candidate_parent_options", "") for row in selected)),
        "collection_count": len({row.get("collection", "") for row in selected}),
        "policy": {
            "selection_only": True,
            "owner_labels_changed": False,
            "source_audio_modified": False,
            "production_policy_changed": False,
        },
    }
    return selected, receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--exclude", type=Path, action="append", default=[],
                        help="CSV batch(es) whose content hashes must not be reissued")
    args = parser.parse_args(argv)
    rows, receipt = select_batch(args.queue, args.limit, args.exclude)
    fields = [
        "batch_row", "id", "path", "content_sha256", "observed_label",
        "candidate_parent_options", "collection", "pack", "sample_family_id",
        "label_source", "owner_label", "owner_note", "owner_reviewer",
        "decision_status",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)
    receipt["batch_out"] = str(args.out.resolve())
    receipt["batch_out_sha256"] = hashlib.sha256(args.out.read_bytes()).hexdigest()
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"selected_rows": len(rows), "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
