#!/usr/bin/env python3
"""Export a breadth-first queue of explicit filename/audio class conflicts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import defaultdict


def load(path):
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return rows[1:] if rows and rows[0].get("record_type") else rows


def collection(path, root):
    rel = os.path.relpath(path, root)
    return rel.split(os.sep)[0] if rel and rel != "." else "<root>"


def stable(row):
    return hashlib.sha256(row["path"].encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictions", required=True)
    ap.add_argument("--source-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--n", type=int, default=400)
    args = ap.parse_args()

    rows = []
    for r in load(args.predictions):
        audio = r.get("full_taxonomy_class") or ""
        name = r.get("filename_class") or ""
        if not audio or not name or audio == name:
            continue
        x = dict(r)
        x["collection"] = collection(x["path"], args.source_root)
        x["boundary_pair"] = f"{audio}  vs  {name}"
        x["boundary_priority"] = float(r.get("full_taxonomy_confidence", 0.0))
        rows.append(x)

    by_pair = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_pair[r["boundary_pair"]][r["collection"]].append(r)
    # Low audio confidence is the most informative boundary; stable hash breaks
    # ties so reruns produce the same manifest.
    for coll_map in by_pair.values():
        for values in coll_map.values():
            values.sort(key=lambda r: (r["boundary_priority"], stable(r)))

    selected = []
    pair_names = sorted(by_pair)
    round_no = 0
    while len(selected) < args.n and pair_names:
        made = 0
        for pair in pair_names:
            coll_map = by_pair[pair]
            colls = sorted(coll_map)
            if round_no < len(colls):
                values = coll_map[colls[round_no]]
                selected.append(values[0])
                made += 1
                if len(selected) >= args.n:
                    break
        if not made:
            break
        round_no += 1

    fields = [
        "boundary_pair", "collection", "path", "filename_class",
        "full_taxonomy_class", "full_taxonomy_confidence",
        "full_taxonomy_similarity", "fused_taxonomy_class", "fusion_source",
        "old_audio_class", "old_audio_confidence", "accepted_at_calibrated_95",
        "human_label", "human_note",
    ]
    final = selected[:args.n]
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in final:
            w.writerow({k: r.get(k, "") for k in fields})
    manifest = [
        {"id": i, "path": r["path"],
         "hint": f"audio: {r['full_taxonomy_class']} | filename: {r['filename_class']}"}
        for i, r in enumerate(final)
    ]
    with open(args.manifest, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"wrote {args.out}: {len(final)} rows")
    print(f"pairs={len(set(r['boundary_pair'] for r in final))} "
          f"collections={len(set(r['collection'] for r in final))}")
    print("top pairs:")
    counts = defaultdict(int)
    for r in final:
        counts[r["boundary_pair"]] += 1
    for pair, n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:20]:
        print(f"  {n:3} {pair}")


if __name__ == "__main__":
    raise SystemExit(main())
