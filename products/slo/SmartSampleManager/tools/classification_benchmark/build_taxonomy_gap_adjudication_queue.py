#!/usr/bin/env python3
"""Export an owner-only queue for mapping fine labels to the frozen head.

This is an adjudication aid, not a relabeller.  Candidate parent classes are
shown as options, but ``owner_label`` stays blank and no option is treated as
ground truth.  Source audio is only hashed for identity and never changed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


# Options are deliberately broad and include OOD.  They express hypotheses
# that an owner can accept or reject after listening; they are not mappings.
CANDIDATE_OPTIONS = {
    "Bass Hit": ("Bass One-Shot", "Bass Loop", "OOD"),
    "Bass Reese": ("Bass One-Shot", "Bass Loop", "OOD"),
    "Synth One-Shot": ("Synth", "OOD"),
    "Pad": ("Synth", "Atmosphere", "OOD"),
    "SFX": ("FX", "Foley", "OOD"),
    "Vocal One-Shot": ("Vocal Phrase", "OOD"),
    "Drum Loop": ("Music Loop", "Percussion", "OOD"),
    "Foley Loop": ("Music Loop", "Foley", "OOD"),
    "Hi-Hat Loop": ("Music Loop", "Percussion", "OOD"),
    "Top Loop": ("Music Loop", "Percussion", "OOD"),
    "Percussion Loop": ("Music Loop", "Percussion", "OOD"),
    "Kick Loop": ("Music Loop", "Percussion", "OOD"),
    "Chord Loop": ("Music Loop", "Synth Loop", "OOD"),
    "Weather/Nature Atmos": ("Atmosphere", "Foley", "OOD"),
    "Crash": ("Hi-Hat", "Percussion", "OOD"),
    "Rimshot": ("Snare", "Percussion", "OOD"),
    "Drum Fill": ("Percussion", "Music Loop", "OOD"),
    "Loop": ("Music Loop", "OOD"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_queue(labels_csv: Path) -> tuple[list[dict[str, str]], dict[str, object]]:
    with labels_csv.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    selected = [row for row in rows if row.get("label", "").strip() in CANDIDATE_OPTIONS]
    seen: set[str] = set()
    queue: list[dict[str, str]] = []
    for row in selected:
        path = Path(row.get("path", "")).expanduser()
        if not path.is_absolute() or not path.is_file():
            raise ValueError(f"candidate source path does not exist: {path}")
        resolved = str(path.resolve())
        if resolved in seen:
            raise ValueError(f"duplicate candidate path: {resolved}")
        seen.add(resolved)
        label = row["label"].strip()
        queue.append({
            "id": str(len(queue) + 1),
            "path": resolved,
            "content_sha256": sha256_file(path),
            "observed_label": label,
            "candidate_parent_options": "|".join(CANDIDATE_OPTIONS[label]),
            "collection": row.get("collection", "").strip(),
            "pack": row.get("pack", "").strip(),
            "sample_family_id": row.get("sample_family_id", "").strip(),
            "label_source": row.get("label_source", "").strip(),
            "owner_label": "",
            "owner_note": "",
            "owner_reviewer": "",
            "decision_status": "pending",
        })
    receipt = {
        "record_type": "slo_taxonomy_gap_adjudication_queue",
        "schema_version": "1.0.0",
        "source_labels_csv": str(labels_csv.resolve()),
        "source_labels_csv_sha256": sha256_file(labels_csv),
        "source_rows": len(rows),
        "queue_rows": len(queue),
        "observed_label_counts": dict(Counter(row["observed_label"] for row in queue)),
        "policy": {
            "candidate_options_are_not_labels": True,
            "owner_labels_blank": True,
            "source_audio_modified": False,
            "production_policy_changed": False,
        },
    }
    return queue, receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args(argv)
    queue, receipt = build_queue(args.labels)
    fields = [
        "id", "path", "content_sha256", "observed_label",
        "candidate_parent_options", "collection", "pack", "sample_family_id",
        "label_source", "owner_label", "owner_note", "owner_reviewer",
        "decision_status",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(queue)
    receipt["queue_out"] = str(args.out.resolve())
    receipt["queue_out_sha256"] = sha256_file(args.out)
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"queue_rows": len(queue), "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
