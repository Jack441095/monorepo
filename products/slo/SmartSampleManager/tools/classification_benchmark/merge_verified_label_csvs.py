#!/usr/bin/env python3
"""Merge verified label CSVs for an exact-label evaluation intersection.

Rows are keyed by path suffix under ``sample_pack_testing``.  Identical
duplicates collapse; conflicting labels are excluded and reported, preventing
an evaluation from silently choosing one adjudication.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


VERSION = "merge_verified_label_csvs_v1"


def _key(path: str, marker: str) -> str:
    value = str(path).replace("\\", "/")
    token = marker.replace("\\", "/").strip("/") + "/"
    return value.split(token, 1)[1] if token in value else value.lstrip("/")


def merge(inputs: list[Path], out_csv: Path, out_report: Path,
          marker: str = "sample_pack_testing") -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for source in inputs:
        with source.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if "path" not in (reader.fieldnames or []) or "label" not in (reader.fieldnames or []):
                raise ValueError(f"{source} must contain path and label columns")
            for row in reader:
                raw_path = (row.get("path") or "").strip()
                label = (row.get("label") or "").strip()
                if not raw_path or not label:
                    continue
                grouped[_key(raw_path, marker)].append({
                    "path": raw_path, "label": label, "source": source.name,
                })
    conflicts: dict[str, list[str]] = {}
    merged: list[dict[str, str]] = []
    identical_duplicates = 0
    for key in sorted(grouped):
        values = grouped[key]
        labels = sorted({value["label"] for value in values})
        if len(labels) > 1:
            conflicts[key] = labels
            continue
        identical_duplicates += max(0, len(values) - 1)
        merged.append({"path": values[-1]["path"], "label": labels[0]})
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "label"])
        writer.writeheader()
        writer.writerows(merged)
    report = {
        "record_type": "slo_verified_label_merge_report",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "inputs": [str(path.resolve()) for path in inputs],
        "marker": marker,
        "n_input_rows": sum(len(values) for values in grouped.values()),
        "n_unique_keys": len(grouped),
        "n_merged_rows": len(merged),
        "n_identical_duplicates_collapsed": identical_duplicates,
        "n_conflicting_keys_excluded": len(conflicts),
        "conflicting_keys": conflicts,
        "output_csv": str(out_csv.resolve()),
    }
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--out-report", type=Path, required=True)
    parser.add_argument("--marker", default="sample_pack_testing")
    args = parser.parse_args()
    report = merge(args.input, args.out_csv, args.out_report, args.marker)
    print(json.dumps({"out_csv": str(args.out_csv), "n_merged_rows": report["n_merged_rows"],
                      "n_conflicting_keys_excluded": report["n_conflicting_keys_excluded"]}, indent=2))


if __name__ == "__main__":
    main()
