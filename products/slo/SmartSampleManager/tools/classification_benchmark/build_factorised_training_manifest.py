#!/usr/bin/env python3
"""Freeze the research inputs for the factorised-head experiment.

The manifest is content-addressed and collection-aware.  It excludes the
sealed 120-item class-gate validation set before any training, removes exact
byte duplicates, and records the split group used by every later benchmark.
It never edits audio or labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def collection_for(path: str) -> tuple[str, str]:
    # The inventory's second component is the vendor/collection group and the
    # third is the pack.  Importing its parser keeps this manifest aligned with
    # the canonical grouped evaluation protocol.
    import sample_library_inventory as inventory
    attr = inventory.attribute(path)
    return str(attr[1]), f"{attr[1]}||{attr[2]}"


def form_for(label: str) -> str:
    if label == "Other/none":
        return "rejection"
    if "Loop" in label:
        return "loop"
    if "Phrase" in label:
        return "phrase"
    if "Fill" in label:
        return "fill"
    return "one-shot"


def build(corpus: Path, validation_manifest: Path) -> dict:
    z = np.load(corpus, allow_pickle=True)
    paths = [os.path.abspath(str(p)) for p in z["paths"]]
    labels = [str(x) for x in z["labels"]]
    if len(paths) != len(labels):
        raise ValueError("corpus paths and labels are misaligned")
    sealed = {
        os.path.abspath(str(row["path"]))
        for row in json.loads(validation_manifest.read_text(encoding="utf-8"))
    }

    rows = []
    excluded_validation = []
    by_content: dict[str, list[dict]] = defaultdict(list)
    for path, label in zip(paths, labels):
        if path in sealed:
            excluded_validation.append(path)
            continue
        if not os.path.exists(path):
            raise ValueError(f"training path is missing: {path}")
        vendor, pack = collection_for(path)
        digest = file_hash(path)
        row = {
            "path": path,
            "content_sha256": digest,
            "label": label,
            "family": label if label != "Other/none" else "rejection",
            "form": form_for(label),
            "vendor": vendor,
            "pack": pack,
            "source": "corpus_v4b_escape_recovered",
        }
        rows.append(row)
        by_content[digest].append(row)

    canonical = []
    duplicate_aliases = []
    for digest, members in sorted(by_content.items()):
        members = sorted(members, key=lambda item: item["path"])
        labels_for_content = {item["label"] for item in members}
        if len(labels_for_content) != 1:
            raise ValueError(f"exact duplicate has conflicting labels: {digest}")
        canonical.append(members[0])
        duplicate_aliases.extend(members[1:])

    vendors = sorted({row["vendor"] for row in canonical})
    return {
        "record_type": "slo_factorised_training_manifest",
        "schema_version": "1.0.0",
        "protocol": {
            "group": "vendor/collection",
            "sealed_validation_manifest": str(validation_manifest.resolve()),
            "duplicate_rule": "one canonical row per complete-file SHA-256",
            "training_embeddings": "corpus_v4b_escape_recovered.npz",
        },
        "summary": {
            "n_corpus_rows": len(paths),
            "n_excluded_sealed_validation": len(excluded_validation),
            "n_training_rows_before_exact_dedup": len(rows),
            "n_training_rows": len(canonical),
            "n_exact_duplicate_aliases": len(duplicate_aliases),
            "n_collections": len(vendors),
            "n_labels": len({row["label"] for row in canonical}),
        },
        "rows": canonical,
        "excluded_validation_paths": sorted(excluded_validation),
        "duplicate_aliases": duplicate_aliases,
        "safety": {
            "read_only": True,
            "source_audio_modified": False,
            "labels_modified": False,
            "validation_rows_used_for_training": False,
            "rename_actions": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--validation-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.corpus, args.validation_manifest)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

