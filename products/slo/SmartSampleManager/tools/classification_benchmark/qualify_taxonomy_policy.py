#!/usr/bin/env python3
"""Qualify full-taxonomy actions from human labels on unseen collections.

This is intentionally fail-closed: no label file, sparse support, or weak
precision can produce an auto-action class. It writes a policy JSON suitable
for ``build_full_taxonomy_rename_plan.py --qualified-classes`` and a detailed
per-class receipt for review.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import tempfile
from collections import Counter, defaultdict


REJECTION_LABELS = {
    "", "__skip__", "Misc/Review", "Other/none", "Unknown", "Not in list",
    "Taxonomy gap", "Not enough info",
}


def wilson_lower(successes, total, z=1.96):
    if not total:
        return 0.0
    p = successes / total
    denom = 1.0 + z * z / total
    centre = p + z * z / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return (centre - spread) / denom


def load_predictions(path):
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if rows and rows[0].get("record_type") and "path" not in rows[0]:
        rows = rows[1:]
    return {os.path.abspath(r["path"]): r for r in rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--predictions", required=True)
    ap.add_argument("--source-root", required=True)
    ap.add_argument("--training-corpus", default=None,
                    help="optional corpus_v2.npz; rows present there are excluded")
    ap.add_argument("--out-policy", required=True)
    ap.add_argument("--out-report", required=True)
    ap.add_argument("--min-support", type=int, default=20)
    ap.add_argument("--min-collections", type=int, default=5)
    ap.add_argument("--precision-floor", type=float, default=0.95)
    args = ap.parse_args()

    if not os.path.isfile(args.labels):
        raise SystemExit(f"label file not found: {args.labels}")
    predictions = load_predictions(args.predictions)
    root = os.path.abspath(args.source_root)
    excluded = set()
    if args.training_corpus:
        z = __import__("numpy").load(args.training_corpus, allow_pickle=True)
        excluded = {os.path.abspath(str(p)) for p in z["paths"]}
    joined = []
    with open(args.labels, newline="") as f:
        for row in csv.DictReader(f):
            label = (row.get("label") or "").strip()
            path = os.path.abspath(row.get("path") or "")
            if (not path or path not in predictions or path in excluded or
                    label in REJECTION_LABELS):
                continue
            rel = os.path.relpath(path, root)
            collection = rel.split(os.sep)[0]
            pred = predictions[path]
            predicted = str(pred.get("fused_taxonomy_class") or
                            pred.get("full_taxonomy_class") or "")
            joined.append({
                "path": path, "label": label, "predicted": predicted,
                "collection": collection,
                "confidence": float(pred.get("fused_taxonomy_confidence") or
                                     pred.get("full_taxonomy_confidence") or 0.0),
                "correct": predicted == label,
            })

    by_class = defaultdict(list)
    for row in joined:
        by_class[row["predicted"]].append(row)
    report = {}
    qualified = []
    for cls in sorted(by_class):
        rows = by_class[cls]
        n = len(rows)
        hits = sum(r["correct"] for r in rows)
        collections = sorted({r["collection"] for r in rows})
        # A class must be right in every collection to be eligible for the
        # product gate; the Wilson bound prevents a small perfect sample from
        # masquerading as evidence.
        lower = wilson_lower(hits, n)
        per_collection = {}
        for collection in collections:
            cr = [r for r in rows if r["collection"] == collection]
            per_collection[collection] = {
                "n": len(cr), "correct": sum(r["correct"] for r in cr),
                "precision": sum(r["correct"] for r in cr) / len(cr),
            }
        eligible = (
            n >= args.min_support and len(collections) >= args.min_collections and
            lower >= args.precision_floor and
            all(v["correct"] == v["n"] for v in per_collection.values())
        )
        report[cls] = {
            "support": n,
            "correct": hits,
            "precision": hits / n if n else 0.0,
            "wilson_lower_95": lower,
            "collections": len(collections),
            "per_collection": per_collection,
            "eligible_for_auto": eligible,
        }
        if eligible:
            qualified.append(cls)

    policy = {
        "schema_version": "1.0.0",
        "qualified_classes": qualified,
        "precision_floor": args.precision_floor,
        "min_support": args.min_support,
        "min_collections": args.min_collections,
        "n_label_rows_joined": len(joined),
        "n_training_rows_excluded": len(excluded),
        "safety": "empty or sparse evidence produces no qualified classes",
    }
    receipt = {
        "schema_version": "1.0.0",
        "n_label_rows_joined": len(joined),
        "n_training_rows_excluded": len(excluded),
        "n_classes_observed": len(report),
        "qualified_classes": qualified,
        "class_report": report,
    }
    for target, payload in ((args.out_policy, policy), (args.out_report, receipt)):
        directory = os.path.dirname(os.path.abspath(target)) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".taxonomy_policy_", suffix=".json",
                                   dir=directory, text=True)
        os.close(fd)
        try:
            with open(tmp, "w") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    print(f"joined labels: {len(joined)}; classes observed: {len(report)}")
    print(f"qualified classes: {qualified}")
    print(f"wrote {args.out_policy}")
    print(f"wrote {args.out_report}")


if __name__ == "__main__":
    raise SystemExit(main())
