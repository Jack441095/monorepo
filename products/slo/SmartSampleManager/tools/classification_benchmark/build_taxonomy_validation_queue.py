#!/usr/bin/env python3
"""Build a breadth-first human validation queue from full-taxonomy predictions.

This is a read-only export. It deliberately mixes high-confidence cases,
name/audio disagreements, low-confidence boundaries, and one-per-collection
coverage rows so that validation estimates both precision and failure modes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import defaultdict


DEFAULT_N = 400
BUCKET_TARGETS = (
    ("high_confidence", 120),
    ("name_audio_disagreement", 140),
    ("low_confidence_boundary", 80),
    ("collection_coverage", 60),
)


def load_rows(path: str):
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if rows and rows[0].get("record_type") == "slo_full_taxonomy_candidate_predictions":
        rows = rows[1:]
    return rows


def collection_for(path: str, source_root: str) -> str:
    rel = os.path.relpath(path, source_root)
    parts = rel.split(os.sep)
    return parts[0] if parts and parts[0] not in (".", "") else "<root>"


def stable_key(row):
    return hashlib.sha256(row["path"].encode()).hexdigest()


def breadth_select(rows, n, caps):
    """Round-robin rows by collection, with a per-collection cap."""
    by_collection = defaultdict(list)
    for row in rows:
        by_collection[row["collection"]].append(row)
    for values in by_collection.values():
        values.sort(key=stable_key)
    selected = []
    for round_no in range(caps):
        for collection in sorted(by_collection):
            values = by_collection[collection]
            if round_no < len(values):
                selected.append(values[round_no])
                if len(selected) >= n:
                    return selected
    return selected


def prepare(row, bucket):
    out = dict(row)
    out["queue_bucket"] = bucket
    out["human_label"] = ""
    out["human_note"] = ""
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictions", required=True)
    ap.add_argument("--source-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--manifest", default=None,
                    help="optional label_tool manifest JSON output")
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    args = ap.parse_args()

    rows = load_rows(args.predictions)
    for row in rows:
        row["collection"] = collection_for(row["path"], args.source_root)
        row["name_audio_disagreement"] = bool(
            row.get("old_audio_class") and
            row.get("old_audio_class") != row.get("full_taxonomy_class")
        ) or bool(
            row.get("filename_class") and
            row.get("filename_class") != row.get("full_taxonomy_class")
        )

    by_path = {row["path"]: row for row in rows}
    selected = {}
    remaining = set(by_path)

    predicates = {
        "high_confidence": lambda r: bool(r.get("accepted_at_calibrated_95")),
        "name_audio_disagreement": lambda r: bool(r.get("name_audio_disagreement")),
        "low_confidence_boundary": lambda r: (
            not r.get("accepted_at_calibrated_95") and
            0.30 <= float(r.get("full_taxonomy_confidence", 0.0)) <= 0.65
        ),
        "collection_coverage": lambda r: True,
    }
    caps = {
        "high_confidence": 4,
        "name_audio_disagreement": 4,
        "low_confidence_boundary": 3,
        "collection_coverage": 1,
    }

    for bucket, target in BUCKET_TARGETS:
        if len(selected) >= args.n:
            break
        candidates = [
            by_path[p] for p in remaining if predicates[bucket](by_path[p])
        ]
        take = min(target, args.n - len(selected))
        for row in breadth_select(candidates, take, caps[bucket]):
            selected[row["path"]] = prepare(row, bucket)
            remaining.discard(row["path"])

    # If a sparse bucket could not fill, top up breadth-first from all remaining
    # rows rather than silently producing a smaller manifest.
    if len(selected) < args.n:
        candidates = [by_path[p] for p in remaining]
        for row in breadth_select(candidates, args.n - len(selected), 99):
            selected[row["path"]] = prepare(row, "top_up")
            remaining.discard(row["path"])

    final = sorted(selected.values(), key=lambda r: (r["queue_bucket"], r["collection"], r["path"]))
    fields = [
        "queue_bucket", "collection", "path", "full_taxonomy_class",
        "full_taxonomy_confidence", "full_taxonomy_similarity",
        "old_audio_class", "old_audio_confidence", "filename_class",
        "accepted_at_calibrated_95", "human_label", "human_note",
    ]
    directory = os.path.dirname(os.path.abspath(args.out)) or "."
    os.makedirs(directory, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in fields} for row in final[:args.n])

    if args.manifest:
        manifest = [
            {"id": i, "path": row["path"],
             "hint": f"model: {row['full_taxonomy_class']}"
                     if row.get("full_taxonomy_class") else ""}
            for i, row in enumerate(final[:args.n])
        ]
        with open(args.manifest, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"wrote {args.manifest}: {len(manifest)} items")

    counts = defaultdict(int)
    collections = set()
    for row in final[:args.n]:
        counts[row["queue_bucket"]] += 1
        collections.add(row["collection"])
    print(f"wrote {args.out}: {len(final[:args.n])} rows")
    print(f"collections covered: {len(collections)}")
    print("buckets:", dict(sorted(counts.items())))


if __name__ == "__main__":
    raise SystemExit(main())
