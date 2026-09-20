#!/usr/bin/env python3
"""Build an owner-adjudication queue from existing reviewed-label CSVs.

Several prior by-ear sessions contain fine-grained labels that are outside the
frozen head.  This command reuses their *reviewed observations* only as queue
evidence: every row still requires an explicit owner parent-class decision.
Complete-file hashes deduplicate aliases, contradictory labels for the same
content are blocked, and hashes already present in a base research manifest are
excluded.  No semantic label or training row is promoted automatically.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "slo_taxonomy_gap_options", SCRIPT_DIR / "build_taxonomy_gap_adjudication_queue.py"
)
_module = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_module)
CANDIDATE_OPTIONS = _module.CANDIDATE_OPTIONS

REQUIRED_FIELDS = {"path", "label", "collection", "pack", "sample_family_id", "labelling_session"}
SKIP_LABELS = {"", "__skip__", "Misc/Review", "Not Bass", "Unknown", "Other/none", "Not enough info"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _base_hashes(path: Path | None) -> set[str]:
    if path is None:
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("rows", [])
    if not isinstance(rows, list):
        raise ValueError("base manifest must be a JSON list or an object with rows")
    hashes = set()
    for row in rows:
        if isinstance(row, dict):
            value = str(row.get("sha256") or row.get("content_sha256") or "").lower()
            if len(value) == 64:
                hashes.add(value)
    return hashes


def build_queue(label_files: list[Path], base_manifest: Path | None = None) -> tuple[list[dict[str, str]], dict[str, Any]]:
    excluded = Counter()
    observations: dict[str, list[dict[str, str]]] = defaultdict(list)
    base_hashes = _base_hashes(base_manifest)
    input_receipts = []
    for source in label_files:
        with source.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not REQUIRED_FIELDS.issubset(reader.fieldnames):
                raise ValueError(f"{source} is missing required reviewed-label fields")
            rows = list(reader)
        input_receipts.append({"path": str(source.resolve()), "sha256": sha256_file(source), "rows": len(rows)})
        for row in rows:
            label = (row.get("label") or "").strip()
            if label in SKIP_LABELS:
                excluded[f"ignored_label:{label or '<blank>'}"] += 1
                continue
            if label not in CANDIDATE_OPTIONS:
                excluded[f"not_a_gap_label:{label}"] += 1
                continue
            if not (row.get("labelling_session") or "").strip():
                excluded["missing_labelling_session"] += 1
                continue
            path = Path((row.get("path") or "").strip()).expanduser()
            if not path.is_absolute() or not path.is_file():
                raise ValueError(f"reviewed source path does not exist: {path}")
            resolved = str(path.resolve())
            content_hash = sha256_file(path)
            if content_hash in base_hashes:
                excluded["already_in_base_manifest"] += 1
                continue
            observations[content_hash].append({
                "path": resolved, "label": label,
                "collection": (row.get("collection") or "").strip(),
                "pack": (row.get("pack") or "").strip(),
                "sample_family_id": (row.get("sample_family_id") or "").strip(),
                "label_source": (row.get("label_source") or "").strip() or f"reviewed_csv:{source.name}",
                "labelling_session": (row.get("labelling_session") or "").strip(),
                "source_file": source.name,
            })

    conflicts = []
    queue: list[dict[str, str]] = []
    duplicate_alias_rows = 0
    for content_hash in sorted(observations):
        values = observations[content_hash]
        labels = sorted({row["label"] for row in values})
        if len(labels) > 1:
            conflicts.append({
                "content_sha256": content_hash,
                "labels": labels,
                "observations": values,
            })
            continue
        values.sort(key=lambda row: (row["source_file"], row["path"], row["labelling_session"]))
        chosen = values[0]
        duplicate_alias_rows += len(values) - 1
        queue.append({
            "id": f"supplement-{len(queue) + 1:04d}",
            "path": chosen["path"], "content_sha256": content_hash,
            "observed_label": chosen["label"],
            "candidate_parent_options": "|".join(CANDIDATE_OPTIONS[chosen["label"]]),
            "collection": chosen["collection"], "pack": chosen["pack"],
            "sample_family_id": chosen["sample_family_id"],
            "label_source": chosen["label_source"], "owner_label": "",
            "owner_note": "", "owner_reviewer": "", "decision_status": "pending",
        })

    receipt = {
        "record_type": "slo_taxonomy_gap_reviewed_csv_queue",
        "schema_version": "1.0.0",
        "inputs": input_receipts,
        "base_manifest": str(base_manifest.resolve()) if base_manifest else None,
        "base_manifest_sha256": sha256_file(base_manifest) if base_manifest else None,
        "source_observation_hashes": len(observations),
        "queue_rows": len(queue),
        "conflict_hashes_blocked": len(conflicts),
        "duplicate_alias_rows_collapsed": duplicate_alias_rows,
        "excluded_counts": dict(excluded),
        "conflicts": conflicts,
        "policy": {
            "reviewed_observations_reused_as_candidates": True,
            "candidate_options_are_not_labels": True,
            "contradictory_hashes_blocked": True,
            "base_hashes_excluded": True,
            "labels_created": False,
            "source_audio_modified": False,
            "production_policy_changed": False,
            "owner_approval_required": True,
        },
    }
    return queue, receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, nargs="+", required=True)
    parser.add_argument("--base-manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args(argv)
    queue, receipt = build_queue(args.labels, args.base_manifest)
    fields = ["id", "path", "content_sha256", "observed_label", "candidate_parent_options",
              "collection", "pack", "sample_family_id", "label_source", "owner_label",
              "owner_note", "owner_reviewer", "decision_status"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(queue)
    receipt["queue_out"] = str(args.out.resolve()); receipt["queue_out_sha256"] = sha256_file(args.out)
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"queue_rows": len(queue), "conflict_hashes_blocked": len(receipt["conflicts"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
