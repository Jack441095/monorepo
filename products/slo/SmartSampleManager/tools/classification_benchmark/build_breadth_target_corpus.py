#!/usr/bin/env python3
"""Build a research corpus at an explicit breadth-label cutoff.

The active labeler writes a larger queue than the owner may want to complete.
This builder accepts the verified CSV only when the requested number of usable
rows has been reached exactly. It merges those rows with an existing corpus by
absolute path, records human corrections to overlapping rows, and refuses any
missing embedding or duplicate-label ambiguity.

The output is research-only. It does not replace a production model, alter a
sealed validation set, or modify source audio.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np


VERSION = "breadth_target_corpus_v1"
DRUM_CLASSES = {"Clap", "Crash", "Drum Loop", "Foley", "Hi-Hat", "Kick",
                "Other/none", "Percussion", "Percussion Loop", "Snare"}
NON_USABLE = {"", "__skip__", "Misc/Review"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_verified_labels(path: Path, target: int) -> list[dict[str, str]]:
    by_path: dict[str, dict[str, str]] = {}
    ordered: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            label = str(row.get("label") or "").strip()
            if label in NON_USABLE:
                continue
            source_path = os.path.abspath(str(row.get("path") or ""))
            if not source_path or not os.path.isfile(source_path):
                raise ValueError(f"labelled source path is missing: {source_path}")
            if source_path in by_path:
                if by_path[source_path]["label"] != label:
                    raise ValueError(f"conflicting labels for path: {source_path}")
                continue
            item = {
                "path": source_path,
                "label": label,
                "percussion_subtype": str(row.get("percussion_subtype") or ""),
                "rejection_reason": str(row.get("rejection_reason") or ""),
            }
            by_path[source_path] = item
            ordered.append(item)
    if len(ordered) != target:
        raise ValueError(f"usable labels are {len(ordered)}, target requires exactly {target}")
    return ordered


def read_embedding_map(path: Path, *, allow_errors: bool = False) -> tuple[dict[str, np.ndarray], int]:
    data = np.load(path, allow_pickle=True)
    if "paths" not in data or "emb" not in data:
        raise ValueError(f"embedding cache lacks paths/emb: {path}")
    paths = [os.path.abspath(str(value)) for value in data["paths"]]
    embeddings = np.asarray(data["emb"], dtype=np.float32)
    errors = [str(value) for value in data["errors"]] if "errors" in data else [""] * len(paths)
    if len(paths) != len(embeddings) or len(paths) != len(errors):
        raise ValueError("embedding paths, vectors, and errors are misaligned")
    # An empty derived cache is a valid intermediate state while the caller is
    # waiting for missing files to be encoded.  Preserve it as an empty map so
    # the build can fail closed with the specific missing-path diagnostic.
    if not paths:
        return {}, 0
    if embeddings.ndim != 2:
        raise ValueError("embedding matrix must be 2-D")
    if len(paths) != len(set(paths)):
        raise ValueError("embedding cache contains duplicate paths")
    if not allow_errors and any(errors):
        raise ValueError(f"embedding cache has {sum(bool(e) for e in errors)} errors")
    result: dict[str, np.ndarray] = {}
    for path_value, vector, error in zip(paths, embeddings, errors):
        if error:
            continue
        if vector.ndim != 1 or not np.isfinite(vector).all():
            raise ValueError(f"invalid embedding for {path_value}")
        result[path_value] = vector
    return result, int(embeddings.shape[1])


def load_base(path: Path) -> tuple[dict[str, dict[str, Any]], int]:
    data = np.load(path, allow_pickle=True)
    required = {"paths", "emb", "labels"}
    if not required.issubset(data.files):
        raise ValueError(f"base corpus lacks keys: {sorted(required - set(data.files))}")
    paths = [os.path.abspath(str(value)) for value in data["paths"]]
    embeddings = np.asarray(data["emb"], dtype=np.float32)
    labels = [str(value) for value in data["labels"]]
    if len(paths) != len(embeddings) or len(paths) != len(labels):
        raise ValueError("base corpus paths, embeddings, and labels are misaligned")
    if len(paths) != len(set(paths)):
        raise ValueError("base corpus contains duplicate paths")
    subtype = [str(value) for value in data["percussion_subtype"]] if "percussion_subtype" in data else [""] * len(paths)
    rejection = [str(value) for value in data["rejection_reason"]] if "rejection_reason" in data else [""] * len(paths)
    raw = [str(value) for value in data["raw_labels"]] if "raw_labels" in data else labels
    source = [str(value) for value in data["source"]] if "source" in data else ["base_corpus"] * len(paths)
    rows = {}
    for p, e, label, raw_label, src, sub, reason in zip(paths, embeddings, labels, raw, source, subtype, rejection):
        if not np.isfinite(e).all():
            raise ValueError(f"non-finite base embedding: {p}")
        rows[p] = {"path": p, "emb": e, "label": label, "raw_label": raw_label,
                   "source": src, "percussion_subtype": sub,
                   "rejection_reason": reason}
    return rows, int(embeddings.shape[1])


def build(base_path: Path, labels_path: Path, embeddings_path: Path,
          target: int, map_non_drum_to_rejection: bool,
          missing_embeddings_path: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    labels = read_verified_labels(labels_path, target)
    base, dimensions = load_base(base_path)
    new_embeddings, new_dimensions = read_embedding_map(embeddings_path)
    if new_embeddings and new_dimensions != dimensions:
        raise ValueError(f"embedding dimensions differ: base={dimensions}, new={new_dimensions}")
    if missing_embeddings_path is not None:
        extra, extra_dimensions = read_embedding_map(missing_embeddings_path)
        if extra and extra_dimensions != dimensions:
            raise ValueError("missing-embedding dimensions differ from base")
        for path, vector in extra.items():
            if path in new_embeddings and not np.array_equal(new_embeddings[path], vector):
                raise ValueError(f"two different embeddings for path: {path}")
            new_embeddings.setdefault(path, vector)

    conflicts: list[dict[str, str]] = []
    appended = 0
    corrected = 0
    for item in labels:
        path = item["path"]
        # Existing corpus rows already carry their validated embedding.  A
        # human correction may therefore be label-only; requiring a fresh
        # path-keyed extraction for an overlap would incorrectly fail closed.
        vector = new_embeddings.get(path)
        if vector is None and path in base:
            vector = np.asarray(base[path]["emb"], dtype=np.float32)
        if vector is None:
            raise ValueError(f"no embedding for labelled path: {path}")
        raw_label = item["label"]
        output_label = "Other/none" if map_non_drum_to_rejection and raw_label not in DRUM_CLASSES else raw_label
        replacement = {"path": path, "emb": vector, "label": output_label,
                       "raw_label": raw_label, "source": f"human_breadth_{target}",
                       "percussion_subtype": item["percussion_subtype"],
                       "rejection_reason": item["rejection_reason"]}
        if path in base:
            if base[path]["label"] != output_label or base[path].get("raw_label", base[path]["label"]) != raw_label:
                conflicts.append({"path": path, "old_label": base[path]["label"],
                                  "new_label": output_label, "raw_label": raw_label})
                corrected += 1
            base[path] = replacement
        else:
            base[path] = replacement
            appended += 1

    ordered = [base[path] for path in sorted(base)]
    matrix = np.asarray([row["emb"] for row in ordered], dtype=np.float32)
    labels_arr = np.asarray([row["label"] for row in ordered], dtype=object)
    payload = {
        "emb": matrix,
        "paths": np.asarray([row["path"] for row in ordered], dtype=object),
        "labels": labels_arr,
        "raw_labels": np.asarray([row["raw_label"] for row in ordered], dtype=object),
        "source": np.asarray([row["source"] for row in ordered], dtype=object),
        "percussion_subtype": np.asarray([row["percussion_subtype"] for row in ordered], dtype=object),
        "rejection_reason": np.asarray([row["rejection_reason"] for row in ordered], dtype=object),
    }
    receipt = {
        "record_type": "slo_breadth_target_corpus",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "target_completed_labels": target,
        "n_base_rows": len(base) - appended,
        "n_output_rows": len(ordered),
        "n_appended_rows": appended,
        "n_human_corrections_overlapping_base": corrected,
        "overlap_corrections": conflicts,
        "embedding_dimensions": dimensions,
        "map_non_drum_to_rejection": map_non_drum_to_rejection,
        "labels_sha256": sha256(labels_path),
        "base_sha256": sha256(base_path),
        "embeddings_sha256": sha256(embeddings_path),
        "missing_embeddings_sha256": sha256(missing_embeddings_path) if missing_embeddings_path else None,
        "safety": {
            "research_only": True,
            "source_audio_modified": False,
            "source_audio_renamed": False,
            "production_model_changed": False,
            "sealed_validation_changed": False,
            "rename_actions": False,
        },
    }
    return payload, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--missing-embeddings", type=Path)
    parser.add_argument("--target-completed", type=int, required=True)
    parser.add_argument("--map-non-drum-to-rejection", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.target_completed < 1:
        raise SystemExit("FAIL CLOSED: target must be positive")
    try:
        payload, receipt = build(args.base, args.labels, args.embeddings,
                                 args.target_completed, args.map_non_drum_to_rejection,
                                 args.missing_embeddings)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise SystemExit(f"FAIL CLOSED: {exc}") from exc
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    directory = args.out.parent
    fd, temporary = tempfile.mkstemp(prefix=".breadth_target_", suffix=".npz", dir=directory)
    os.close(fd)
    try:
        np.savez_compressed(temporary, **payload)
        os.replace(temporary, args.out)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    receipt["output"] = str(args.out.resolve())
    receipt["receipt"] = str(args.receipt.resolve())
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
