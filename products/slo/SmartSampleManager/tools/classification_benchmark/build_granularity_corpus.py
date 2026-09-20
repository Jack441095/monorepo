#!/usr/bin/env python3
"""Build an aligned research corpus from the normalized granularity labels.

The granularity sprint mostly relabels files that already have cached
Perch+CLAP embeddings.  This builder joins those labels by absolute path and
encodes only the small remainder supplied through ``--missing-embeddings``.
It refuses missing paths, duplicate labels, or stale embedding rows and never
touches source audio.  The output is deliberately a new research corpus; it
does not replace the production model or the sealed evaluation set.
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
DEFAULT_LABELS = SD / "ground_truth" / "SLO_GT_V1" / "labels.csv"
DEFAULT_BASE = SD / "corpus_v4b_escape_recovered.npz"
DEFAULT_OUT = SD / "corpus_granularity_v1.npz"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_labels(path: Path) -> list[dict[str, str]]:
    rows = []
    seen: dict[str, str] = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            p = os.path.abspath(row.get("path", ""))
            label = (row.get("label") or "").strip()
            if not p or not label:
                raise SystemExit("FAIL CLOSED: empty path or label in ground truth")
            if p in seen and seen[p] != label:
                raise SystemExit(f"FAIL CLOSED: conflicting ground-truth path: {p}")
            if p not in seen:
                seen[p] = label
                row["path"] = p
                rows.append(row)
    return rows


def read_embeddings(path: Path) -> dict[str, np.ndarray]:
    z = np.load(path, allow_pickle=True)
    if "paths" not in z or "emb" not in z:
        raise SystemExit(f"FAIL CLOSED: embedding corpus lacks paths/emb: {path}")
    paths = [os.path.abspath(str(p)) for p in z["paths"]]
    emb = np.asarray(z["emb"], dtype=np.float32)
    if len(paths) != len(emb):
        raise SystemExit("FAIL CLOSED: base paths/embeddings misaligned")
    result: dict[str, np.ndarray] = {}
    for p, e in zip(paths, emb):
        if p in result and not np.array_equal(result[p], e):
            raise SystemExit(f"FAIL CLOSED: duplicate base path has two embeddings: {p}")
        result[p] = e
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    ap.add_argument("--base", type=Path, default=DEFAULT_BASE)
    ap.add_argument("--missing-embeddings", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    labels = read_labels(args.labels)
    embeddings = read_embeddings(args.base)
    missing = read_embeddings(args.missing_embeddings)
    for p, e in missing.items():
        if p in embeddings and not np.array_equal(embeddings[p], e):
            raise SystemExit(f"FAIL CLOSED: base/missing embedding mismatch: {p}")
        embeddings.setdefault(p, e)

    rows = []
    for row in labels:
        p = row["path"]
        if not os.path.isfile(p):
            raise SystemExit(f"FAIL CLOSED: labelled source path is missing: {p}")
        if p not in embeddings:
            raise SystemExit(
                f"FAIL CLOSED: no embedding for labelled path: {p}\n"
                "encode it explicitly; do not silently drop a human label")
        rows.append(row)

    X = np.asarray([embeddings[r["path"]] for r in rows], dtype=np.float32)
    if not np.isfinite(X).all():
        raise SystemExit("FAIL CLOSED: non-finite embedding in output")
    labels_arr = np.asarray([r["label"] for r in rows], dtype=object)
    paths_arr = np.asarray([r["path"] for r in rows], dtype=object)
    np.savez_compressed(
        args.out,
        emb=X,
        paths=paths_arr,
        labels=labels_arr,
        source=np.asarray([r.get("label_source", "") for r in rows], dtype=object),
        percussion_subtype=np.asarray(
            [r.get("percussion_subtype", "") for r in rows], dtype=object),
        rejection_reason=np.asarray(
            [r.get("rejection_reason", "") for r in rows], dtype=object),
    )
    receipt = {
        "record_type": "slo_granularity_corpus",
        "schema_version": "1.0.0",
        "safety": "research-only; source audio read-only; production unchanged",
        "n_rows": len(rows),
        "embedding_dimensions": int(X.shape[1]),
        "n_base_embeddings": len(read_embeddings(args.base)),
        "n_missing_embeddings_supplied": len(missing),
        "n_paths_requiring_missing_embeddings": sum(
            r["path"] not in read_embeddings(args.base) for r in rows),
        "labels_sha256": sha256(args.labels),
        "base_sha256": sha256(args.base),
        "missing_embeddings_sha256": sha256(args.missing_embeddings),
        "output": str(args.out.resolve()),
        "class_counts": {
            str(k): int(v) for k, v in zip(*np.unique(labels_arr, return_counts=True))
        },
    }
    receipt_path = args.out.with_suffix(".json")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
