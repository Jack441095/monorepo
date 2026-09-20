#!/usr/bin/env python3
"""Combine corpus_v2 with deduplicated, human-labelled new embeddings."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile

import numpy as np


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_rows(path):
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if rows and rows[0].get("record_type"):
        rows = rows[1:]
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--embeddings", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--metadata", required=True)
    args = ap.parse_args()

    base = np.load(args.base, allow_pickle=True)
    extra = np.load(args.embeddings, allow_pickle=True)
    rows = manifest_rows(args.manifest)
    extra_paths = [os.path.abspath(str(p)) for p in extra["paths"]]
    errors = list(extra["errors"])
    if len(rows) != len(extra_paths):
        raise SystemExit(f"manifest/embedding row mismatch: {len(rows)} vs {len(extra_paths)}")
    if any(bool(e) for e in errors):
        raise SystemExit("FAIL CLOSED: extra embedding artifact contains errors")
    labels = [str(r["label"]) for r in rows]
    if len(set(extra_paths)) != len(extra_paths):
        raise SystemExit("FAIL CLOSED: duplicate extra embedding paths")

    base_paths = [os.path.abspath(str(p)) for p in base["paths"]]
    if set(base_paths) & set(extra_paths):
        raise SystemExit("FAIL CLOSED: extra corpus path already exists in base corpus")
    emb = np.asarray(extra["emb"], dtype=np.float32)
    if emb.ndim != 2 or emb.shape[1] != np.asarray(base["emb"]).shape[1]:
        raise SystemExit("FAIL CLOSED: embedding dimensions do not match")
    if not np.isfinite(emb).all():
        raise SystemExit("FAIL CLOSED: non-finite extra embeddings")

    paths = np.asarray(base_paths + extra_paths, dtype=object)
    labels_all = np.concatenate([
        np.asarray(base["labels"]).astype(str), np.asarray(labels).astype(str)
    ])
    emb_all = np.vstack([np.asarray(base["emb"], dtype=np.float32), emb])
    source = np.concatenate([
        np.asarray(base["source"]).astype(str),
        np.asarray(["human_external"] * len(rows)).astype(str),
    ])
    subtype = np.concatenate([
        np.asarray(base["percussion_subtype"]).astype(str),
        np.asarray([""] * len(rows)).astype(str),
    ])
    rejection = np.concatenate([
        np.asarray(base["rejection_reason"]).astype(str),
        np.asarray([""] * len(rows)).astype(str),
    ])

    directory = os.path.dirname(os.path.abspath(args.out)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".corpus_v3_", suffix=".npz", dir=directory)
    os.close(fd)
    try:
        np.savez(tmp, emb=emb_all, paths=paths, labels=labels_all,
                 source=source, percussion_subtype=subtype,
                 rejection_reason=rejection)
        os.replace(tmp, args.out)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

    meta = {
        "schema_version": "1.0.0",
        "base_corpus": os.path.abspath(args.base),
        "extra_manifest": os.path.abspath(args.manifest),
        "extra_embeddings": os.path.abspath(args.embeddings),
        "n_base": len(base_paths), "n_extra": len(extra_paths),
        "n_total": len(paths), "n_classes": len(set(labels_all)),
        "class_counts": {c: int((labels_all == c).sum())
                         for c in sorted(set(labels_all))},
        "base_sha256": sha256(args.base),
        "extra_sha256": sha256(args.embeddings),
        "safety": "derived corpus only; source audio was not modified",
    }
    with open(args.metadata, "w") as f:
        json.dump(meta, f, indent=2, sort_keys=True)
    print(f"wrote {args.out}: {len(paths)} rows, {len(set(labels_all))} classes")
    print(f"wrote {args.metadata}")


if __name__ == "__main__":
    raise SystemExit(main())

