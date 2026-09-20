#!/usr/bin/env python3
"""Apply the audited granularity labels to the fixed v4b row set.

This is a diagnostic companion to ``build_granularity_corpus.py``.  It keeps
every v4b path and embedding in exactly the same order, changing only labels
for paths covered by the newly integrated human ground truth.  That makes the
before/after evaluation comparable without pretending that unlabeled v4b rows
are new human evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np

SD = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path,
                    default=SD / "corpus_v4b_escape_recovered.npz")
    ap.add_argument("--labels", type=Path,
                    default=SD / "ground_truth" / "SLO_GT_V1" / "labels.csv")
    ap.add_argument("--out", type=Path,
                    default=SD / "corpus_granularity_relabelled_v1.npz")
    args = ap.parse_args()

    z = np.load(args.base, allow_pickle=True)
    paths = [os.path.abspath(str(p)) for p in z["paths"]]
    X = np.asarray(z["emb"], dtype=np.float32)
    old = np.asarray(z["labels"]).astype(str)
    if len(paths) != len(X) or len(paths) != len(old) or len(set(paths)) != len(paths):
        raise SystemExit("FAIL CLOSED: base corpus paths/labels/embeddings misaligned")

    updates: dict[str, str] = {}
    with args.labels.open(newline="") as f:
        for row in csv.DictReader(f):
            p = os.path.abspath(row.get("path", ""))
            label = (row.get("label") or "").strip()
            if not p or not label:
                raise SystemExit("FAIL CLOSED: empty ground-truth path or label")
            if p in updates and updates[p] != label:
                raise SystemExit(f"FAIL CLOSED: conflicting ground-truth label: {p}")
            updates[p] = label

    new = old.copy()
    changed = []
    for i, p in enumerate(paths):
        if p in updates and updates[p] != old[i]:
            changed.append({"path": p, "old": old[i], "new": updates[p]})
            new[i] = updates[p]

    np.savez_compressed(
        args.out,
        emb=X,
        paths=np.asarray(paths, dtype=object),
        labels=new,
        source=np.asarray(z["source"], dtype=object) if "source" in z else np.asarray([""] * len(paths)),
        percussion_subtype=np.asarray(z["percussion_subtype"], dtype=object)
        if "percussion_subtype" in z else np.asarray([""] * len(paths)),
        rejection_reason=np.asarray(z["rejection_reason"], dtype=object)
        if "rejection_reason" in z else np.asarray([""] * len(paths)),
    )
    receipt = {
        "record_type": "slo_granularity_label_effect_corpus",
        "schema_version": "1.0.0",
        "safety": "research-only; fixed base rows; source audio read-only",
        "n_rows": len(paths),
        "n_label_updates": len(changed),
        "n_ground_truth_paths_in_base": sum(p in set(paths) for p in updates),
        "update_pairs": {},
        "base_sha256": sha256(args.base),
        "labels_sha256": sha256(args.labels),
        "output": str(args.out.resolve()),
    }
    from collections import Counter
    receipt["update_pairs"] = {
        f"{old} -> {new}": int(n)
        for (old, new), n in Counter((x["old"], x["new"]) for x in changed).items()
    }
    args.out.with_suffix(".json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
