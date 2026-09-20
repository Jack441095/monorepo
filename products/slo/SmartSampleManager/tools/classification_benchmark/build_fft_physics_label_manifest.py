#!/usr/bin/env python3
"""Create a candidate-hidden, stratified human-review manifest.

The input is an evidence-only FFT/physics queue.  Candidate predictions and
feature values are used solely for deterministic sampling, then removed from
the reviewer-facing rows.  The output is a label request, never a label set or
training mutation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path


SD = Path(__file__).resolve().parent
BUCKETS = ("loop_temporal", "transient_temporal", "evidence_disagreement",
           "bright_spectral", "random_audit")
QUOTAS = {"loop_temporal": 0.30, "transient_temporal": 0.20,
          "evidence_disagreement": 0.20, "bright_spectral": 0.10,
          "random_audit": 0.20}
CSV_FIELDS = ("id", "path", "content_sha256", "review_prompt", "human_label",
              "reviewer", "note")


def _read_queue(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("record_type") != "slo_physics_review_queue":
        raise ValueError("input is not a physics review queue")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("auto_action_allowed")):
        raise ValueError("input queue is not review-only")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("input queue has no rows")
    return rows


def _stable(path: str, seed: int) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}:{path}".encode()).digest()[:8], "big")


def _bucket(row: dict) -> str:
    lanes = set(row.get("physics_candidate_lanes") or [])
    form = str(row.get("form_evidence") or "")
    if form == "loop_temporal_evidence" and "transient_decay_evidence" in lanes:
        return "evidence_disagreement"
    if form == "transient_temporal_evidence" and "repeating_temporal_evidence" in lanes:
        return "evidence_disagreement"
    if "repeating_temporal_evidence" in lanes or form == "loop_temporal_evidence":
        return "loop_temporal"
    if "transient_decay_evidence" in lanes or form == "transient_temporal_evidence":
        return "transient_temporal"
    if "high_frequency_evidence" in lanes:
        return "bright_spectral"
    return "random_audit"


def _take(items: list[dict], count: int, seed: int) -> list[dict]:
    items = sorted(items, key=lambda row: (_stable(str(row["path"]), seed), str(row["path"])))
    return items[:max(0, count)]


def _read_excluded_paths(paths: list[Path] | None) -> set[str]:
    excluded: set[str] = set()
    for source in paths or []:
        with source.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if "path" not in (reader.fieldnames or []):
                raise ValueError(f"exclude CSV is missing a path column: {source}")
            for row in reader:
                value = str(row.get("path") or "").strip()
                if value:
                    excluded.add(os.path.abspath(value))
    return excluded


def build_manifest(source: Path, json_out: Path, csv_out: Path,
                   limit: int = 200, seed: int = 42,
                   exclude_csvs: list[Path] | None = None) -> dict:
    rows = _read_queue(source)
    excluded_paths = _read_excluded_paths(exclude_csvs)
    unique: dict[str, dict] = {}
    duplicate_count = 0
    excluded_count = 0
    for row in rows:
        path = str(row.get("fft_local_path") or "")
        digest = str(row.get("content_sha256") or "").lower()
        if not path or not os.path.isfile(path) or not digest:
            continue
        if os.path.abspath(path) in excluded_paths:
            excluded_count += 1
            continue
        key = digest or os.path.abspath(path)
        if key in unique:
            duplicate_count += 1
            continue
        unique[key] = row
    eligible = list(unique.values())
    if limit < 0:
        raise ValueError("limit must be non-negative")
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in eligible:
        buckets[_bucket(row)].append(row)
    selected: list[dict] = []
    selected_keys: set[str] = set()
    for bucket in BUCKETS:
        count = min(len(buckets[bucket]), int(round(limit * QUOTAS[bucket])))
        for row in _take(buckets[bucket], count, seed):
            key = str(row.get("content_sha256") or row.get("fft_local_path"))
            selected.append(row)
            selected_keys.add(key)
    if len(selected) < limit:
        remaining = [row for row in eligible
                     if str(row.get("content_sha256") or row.get("fft_local_path")) not in selected_keys]
        selected.extend(_take(remaining, limit - len(selected), seed + 1))
    selected = selected[:limit]
    selected.sort(key=lambda row: (str(row.get("content_sha256")), str(row.get("fft_local_path"))))

    review_rows = []
    for index, row in enumerate(selected, 1):
        review_rows.append({
            "id": f"fftphys-{index:04d}",
            "path": str(row["fft_local_path"]),
            "content_sha256": str(row["content_sha256"]),
            "review_prompt": (
                "Listen to the audio and enter the best supported frozen class; "
                "use UNKNOWN/OOD when no class is defensible. Do not infer from the filename."
            ),
            "human_label": "",
            "reviewer": "",
            "note": "",
        })
    source_bucket_counts = Counter(_bucket(row) for row in eligible)
    selected_bucket_counts = Counter(_bucket(row) for row in selected)
    payload = {
        "record_type": "slo_fft_physics_label_manifest",
        "schema_version": "1.0.0",
        "method_version": "fft_physics_label_manifest_v2",
        "source_queue": str(source.resolve()),
        "seed": seed,
        "n_source_rows": len(rows), "n_eligible": len(eligible),
        "n_selected": len(review_rows), "duplicate_content_excluded": duplicate_count,
        "known_label_path_excluded": excluded_count,
        "excluded_csvs": [str(path.resolve()) for path in (exclude_csvs or [])],
        "source_bucket_counts": dict(sorted(source_bucket_counts.items())),
        "selected_bucket_counts": dict(sorted(selected_bucket_counts.items())),
        "rows": review_rows,
        "safety": {
            "read_only": True, "candidate_fields_hidden": True,
            "semantic_labels_created": False, "labels_created": False,
            "training_data_created": False, "source_audio_modified": False,
            "rename_actions": False, "auto_action_allowed": False,
            "human_approval_required": True,
        },
    }
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(review_rows)
    payload["csv_out"] = str(csv_out.resolve())
    payload["csv_sha256"] = hashlib.sha256(csv_out.read_bytes()).hexdigest()
    json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-queue", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--csv-out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--exclude-csv", type=Path, action="append", default=[],
                        help="verified label CSV whose paths must not enter this review batch")
    args = parser.parse_args()
    payload = build_manifest(args.source_queue, args.json_out, args.csv_out,
                             args.limit, args.seed, args.exclude_csv)
    print(json.dumps({"n_selected": payload["n_selected"],
                      "selected_bucket_counts": payload["selected_bucket_counts"],
                      "json_out": str(args.json_out), "csv_out": str(args.csv_out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
