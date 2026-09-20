#!/usr/bin/env python3
"""Build a deduplicated embedding plan from consensus human labels."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from collections import defaultdict

REJECT = {"", "__skip__", "Misc/Review", "Other/none"}


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_jsonl(path, header, rows):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".label_manifest_", suffix=".jsonl",
                               dir=directory, text=True)
    os.close(fd)
    try:
        with open(tmp, "w") as f:
            f.write(json.dumps(header, sort_keys=True) + "\n")
            for row in rows:
                f.write(json.dumps(row, sort_keys=True) + "\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", nargs="+", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out-plan", required=True)
    args = ap.parse_args()

    labels = defaultdict(list)
    provenance = defaultdict(list)
    for filename in args.labels:
        with open(filename, newline="") as f:
            for row in csv.DictReader(f):
                path = os.path.abspath(row.get("path") or "")
                label = (row.get("label") or "").strip()
                if path and label not in REJECT:
                    labels[path].append(label)
                    provenance[path].append(os.path.basename(filename))
    consensus = {p: next(iter(set(v))) for p, v in labels.items()
                 if len(set(v)) == 1}

    import numpy as np
    z = np.load(args.corpus, allow_pickle=True)
    corpus_paths = {os.path.abspath(str(p)) for p in z["paths"]}
    corpus_hashes = {file_hash(p) for p in corpus_paths if os.path.isfile(p)}

    rows = []
    skipped = defaultdict(int)
    for path in sorted(consensus):
        if path in corpus_paths:
            skipped["already_in_corpus"] += 1
            continue
        if not os.path.isfile(path):
            skipped["missing"] += 1
            continue
        if file_hash(path) in corpus_hashes:
            skipped["duplicate_content"] += 1
            continue
        rows.append({
            "path": path,
            "label": consensus[path],
            "label_sources": provenance[path],
            "decision": {"action": "review"},
        })

    header = {
        "record_type": "slo_label_embedding_manifest",
        "schema_version": "1.0.0",
        "n_rows": len(rows),
        "label_files": [os.path.abspath(p) for p in args.labels],
        "corpus": os.path.abspath(args.corpus),
        "consensus_labels": len(consensus),
        "skipped": dict(skipped),
        "safety": "derived embedding plan only; no source filesystem mutation",
    }
    write_jsonl(args.out_plan, header, rows)
    print(f"wrote {args.out_plan}: {len(rows)} new audio files")
    print(f"consensus labels={len(consensus)} skipped={dict(skipped)}")


if __name__ == "__main__":
    raise SystemExit(main())

