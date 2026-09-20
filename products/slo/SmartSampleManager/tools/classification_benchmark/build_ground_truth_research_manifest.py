#!/usr/bin/env python3
"""Build a research manifest from the reviewed SLO ground-truth labels.

Only labels that already exist in ``ground_truth/SLO_GT_V1/labels.csv`` are
carried forward.  Fine-grained labels outside the frozen acoustic-head
taxonomy are excluded rather than guessed.  The reviewed ``Other/none`` label
is represented as explicit OOD/rejection evidence.  Audio is read only to
bind a SHA-256; it is never copied or modified.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any


KNOWN_CLASSES = {
    "Kick", "Snare", "Hi-Hat", "Clap", "Percussion", "Bass One-Shot",
    "Bass Loop", "Synth", "Synth Loop", "Vocal Phrase", "Vocal Loop",
    "Impact", "Riser", "Foley", "FX", "Atmosphere", "Music Loop",
}
REJECTION_LABEL = "Other/none"
REQUIRED_LABEL_FIELDS = {"path", "label", "collection", "pack", "sample_family_id"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _vendor_id(row: dict[str, str]) -> str:
    """Use the reviewed collection as a transparent vendor proxy.

    The legacy ground-truth schema has no separate vendor field.  Keeping the
    collection value visible is safer than silently pretending a pack or
    personal folder is a verified vendor identity; the manifest records this
    provenance in ``vendor_id_source``.
    """
    return row.get("collection", "").strip()


def build_manifest(labels_csv: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with labels_csv.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_LABEL_FIELDS.issubset(reader.fieldnames):
            raise ValueError("ground-truth CSV is missing required fields")
        source_rows = list(reader)

    selected: list[dict[str, Any]] = []
    excluded = Counter()
    seen_paths: dict[str, str] = {}
    for row in source_rows:
        label = row.get("label", "").strip()
        if label not in KNOWN_CLASSES and label != REJECTION_LABEL:
            excluded[label or "<blank>"] += 1
            continue
        path = Path(row.get("path", "")).expanduser()
        if not path.is_absolute() or not path.is_file():
            raise ValueError(f"selected ground-truth path does not exist: {path}")
        resolved = str(path.resolve())
        prior_label = seen_paths.get(resolved)
        if prior_label is not None and prior_label != label:
            raise ValueError(f"conflicting reviewed labels for path: {resolved}")
        if prior_label is not None:
            raise ValueError(f"duplicate reviewed path: {resolved}")
        seen_paths[resolved] = label

        is_ood = label == REJECTION_LABEL
        content_hash = row.get("content_sha256", "").strip().lower()
        if len(content_hash) != 64:
            content_hash = sha256_file(path)
        if len(content_hash) != 64:
            raise ValueError(f"could not derive SHA-256 for {resolved}")

        selected.append({
            "sample_id": len(selected) + 1,
            "path": resolved,
            "filename": path.name,
            "sha256": content_hash,
            "vendor_id": _vendor_id(row),
            "vendor_id_source": "ground_truth.collection_proxy",
            "pack_id": row.get("pack", "").strip(),
            "source_family": row.get("sample_family_id", "").strip(),
            "expected_subcategory": "OOD" if is_ood else label,
            "ood": is_ood,
            "ood_reason": row.get("rejection_reason", "").strip() if is_ood else "",
            "label_authority": "HUMAN_REVIEWED_GROUND_TRUTH",
            "label_source": row.get("label_source", "").strip(),
            "review_status": "reviewed",
            "reviewer_id": row.get("labelling_session", "").strip(),
            "is_impulse_response": row.get("is_impulse_response", "false").strip().lower() == "true",
            "note": row.get("note", "").strip(),
        })

    receipt = {
        "record_type": "slo_ground_truth_research_manifest_build",
        "schema_version": "1.0.0",
        "source_labels_csv": str(labels_csv.resolve()),
        "source_labels_csv_sha256": sha256_file(labels_csv),
        "source_rows": len(source_rows),
        "selected_rows": len(selected),
        "known_rows": sum(not row["ood"] for row in selected),
        "ood_rows": sum(row["ood"] for row in selected),
        "selected_label_counts": dict(Counter(row["expected_subcategory"] for row in selected)),
        "excluded_label_counts": dict(excluded),
        "vendor_proxy_count": len({row["vendor_id"] for row in selected}),
        "source_family_count": len({row["source_family"] for row in selected if row["source_family"]}),
        "policy": {
            "fine_grained_unmapped_labels_excluded": True,
            "other_none_mapped_to_explicit_ood": True,
            "labels_invented": False,
            "audio_copied": False,
            "audio_modified": False,
            "production_policy_changed": False,
        },
    }
    return selected, receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args(argv)
    rows, receipt = build_manifest(args.labels)
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_out.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    receipt["manifest_out"] = str(args.manifest_out.resolve())
    receipt["manifest_out_sha256"] = sha256_file(args.manifest_out)
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"selected_rows": len(rows), "manifest_out": str(args.manifest_out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
