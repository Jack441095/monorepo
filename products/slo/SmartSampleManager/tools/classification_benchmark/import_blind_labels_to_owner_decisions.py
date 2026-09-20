#!/usr/bin/env python3
"""Join blind by-ear labels into the owner-review CSV without promotion.

The blind manifest and completed label CSV are joined by exact ID and absolute
path.  Agreement with the candidate prediction becomes an ``approve``
candidate, disagreement becomes ``reject``, and a skip/escape becomes
``defer``.  The result still requires the independent approval-receipt bridge;
this command never changes the plan or filesystem.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_decisions(queue_path: Path, manifest_path: Path, labels_path: Path,
                    reviewer: str) -> list[dict[str, str]]:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer must be non-empty")
    queue = _read_csv(queue_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("blind manifest must be a non-empty JSON list")
    labels = _read_csv(labels_path)
    queue_by_path: dict[str, dict[str, str]] = {}
    for row in queue:
        path = os.path.abspath(str(row.get("path", "")))
        if not path or path in queue_by_path:
            raise ValueError(f"queue has missing or duplicate path: {path}")
        queue_by_path[path] = dict(row)
    manifest_by_id: dict[int, dict[str, Any]] = {}
    for row in manifest:
        try:
            row_id = int(row["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("manifest contains an invalid id") from exc
        path = os.path.abspath(str(row.get("path", "")))
        if row_id in manifest_by_id or not path:
            raise ValueError(f"manifest has missing or duplicate id/path: {row_id}")
        if path not in queue_by_path:
            raise ValueError(f"manifest path is not in owner queue: {path}")
        manifest_by_id[row_id] = {**row, "path": path}

    labels_by_id: dict[int, dict[str, str]] = {}
    for row in labels:
        try:
            row_id = int(row.get("id", ""))
        except ValueError as exc:
            raise ValueError("label CSV contains an invalid id") from exc
        if row_id in labels_by_id:
            raise ValueError(f"label CSV has duplicate id: {row_id}")
        manifest_row = manifest_by_id.get(row_id)
        if manifest_row is None:
            raise ValueError(f"label id is not in blind manifest: {row_id}")
        if os.path.abspath(str(row.get("path", ""))) != manifest_row["path"]:
            raise ValueError(f"label path does not match manifest for id {row_id}")
        labels_by_id[row_id] = row

    out = [dict(row) for row in queue]
    out_by_path = {os.path.abspath(str(row["path"])): row for row in out}
    for row_id, label_row in labels_by_id.items():
        manifest_row = manifest_by_id[row_id]
        target = out_by_path[manifest_row["path"]]
        label = str(label_row.get("label", "")).strip()
        if not label or label == "__skip__":
            decision, note = "defer", "blind_label_skip"
        elif label == str(target.get("predicted_class", "")):
            decision, note = "approve", "independent_label_agrees"
        else:
            decision, note = "reject", f"independent_label={label}"
        extra_note = str(label_row.get("note", "")).strip()
        if extra_note:
            note = f"{note}; {extra_note}"
        target["owner_decision"] = decision
        target["owner_reviewer"] = reviewer
        target["owner_note"] = note
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = build_decisions(args.queue, args.manifest, args.labels, args.reviewer)
    if not rows:
        raise SystemExit("queue is empty")
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    counts = {}
    for row in rows:
        value = row.get("owner_decision", "")
        counts[value] = counts.get(value, 0) + 1
    print(json.dumps({"rows": len(rows), "decisions": counts, "out": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
