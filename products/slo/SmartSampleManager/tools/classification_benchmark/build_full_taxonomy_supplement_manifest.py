#!/usr/bin/env python3
"""Build a conflict-safe full-taxonomy supplement from all label CSVs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from collections import defaultdict

FULL_CLASSES = {
    "Bass Hit", "Bass Loop", "Bass Reese", "Chord Loop", "Clap", "Crash",
    "Drum Fill", "Drum Loop", "Foley", "Foley Loop", "Hi-Hat", "Hi-Hat Loop",
    "Kick", "Kick Loop", "Loop", "Pad", "Percussion", "Percussion Loop",
    "Rimshot", "SFX", "Snare", "Synth Loop", "Synth One-Shot", "Vocal Loop",
    "Vocal One-Shot", "Weather/Nature Atmos", "Impact", "Riser", "Atmosphere",
    "Top Loop",
}
LABEL_MAP = {"Reese Bass": "Bass Reese"}
REJECT = {"", "__skip__", "Misc/Review", "Other/none", "Unknown",
          "Not in list", "Not enough info", "Taxonomy gap"}


def full_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_jsonl(path, header, rows):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".taxonomy_supplement_", suffix=".jsonl",
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
    for filename in sorted(args.labels):
        with open(filename, newline="") as f:
            for row in csv.DictReader(f):
                path = os.path.abspath(row.get("path") or "")
                label = LABEL_MAP.get((row.get("label") or "").strip(),
                                      (row.get("label") or "").strip())
                if path and label not in REJECT and label in FULL_CLASSES:
                    labels[path].append(label)
                    provenance[path].append(os.path.basename(filename))
    consensus = {p: next(iter(set(v))) for p, v in labels.items()
                 if len(set(v)) == 1}
    conflicts = {p: v for p, v in labels.items() if len(set(v)) > 1}

    import numpy as np
    z = np.load(args.corpus, allow_pickle=True)
    corpus_paths = {os.path.abspath(str(p)) for p in z["paths"]}
    corpus_hashes = {full_hash(p) for p in corpus_paths if os.path.isfile(p)}
    rows, skipped = [], defaultdict(int)
    for path in sorted(consensus):
        if path in corpus_paths:
            skipped["already_in_corpus"] += 1
            continue
        if not os.path.isfile(path):
            skipped["missing"] += 1
            continue
        if full_hash(path) in corpus_hashes:
            skipped["duplicate_content"] += 1
            continue
        rows.append({"path": path, "label": consensus[path],
                     "label_sources": provenance[path],
                     "decision": {"action": "review"}})

    header = {
        "record_type": "slo_full_taxonomy_supplement_manifest",
        "schema_version": "1.0.0", "n_rows": len(rows),
        "n_consensus": len(consensus), "n_conflicting_paths": len(conflicts),
        "skipped": dict(skipped), "taxonomy_classes": sorted(FULL_CLASSES),
        "safety": "derived embedding plan only; no source filesystem mutation",
    }
    write_jsonl(args.out_plan, header, rows)
    print(f"wrote {args.out_plan}: {len(rows)} rows")
    print(f"consensus={len(consensus)} conflicts={len(conflicts)} skipped={dict(skipped)}")


if __name__ == "__main__":
    raise SystemExit(main())

