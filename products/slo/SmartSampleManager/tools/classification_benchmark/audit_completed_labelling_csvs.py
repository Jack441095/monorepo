#!/usr/bin/env python3
"""Read-only integrity audit for completed SLO labelling CSVs.

This validates label-file provenance before any later dataset integration. It
does not infer labels, require source audio to be present, modify CSVs, or
promote reviewer decisions into gold data.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any


NOTE_REQUIRED = {"Unknown", "Not in list", "Taxonomy gap"}


def audit_one(csv_path: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list) or not manifest:
        raise ValueError(f"manifest is empty or malformed: {manifest_path}")
    expected = {int(item["id"]): str(item["path"]) for item in manifest}
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    ids: list[int] = []
    duplicate_ids: list[int] = []
    duplicate_paths: list[str] = []
    seen_paths: set[str] = set()
    missing_labels: list[int] = []
    invalid_escapes: list[int] = []
    path_mismatches: list[int] = []
    unknown_ids: list[int] = []
    skipped = 0
    labels = Counter()
    for row in rows:
        raw_id = str(row.get("id", ""))
        if not raw_id.isdigit():
            raise ValueError(f"non-numeric id in {csv_path}: {raw_id!r}")
        ident = int(raw_id)
        ids.append(ident)
        if ident in ids[:-1]:
            duplicate_ids.append(ident)
        path = str(row.get("path", ""))
        if path in seen_paths:
            duplicate_paths.append(path)
        seen_paths.add(path)
        if ident not in expected:
            unknown_ids.append(ident)
        elif path != expected[ident]:
            path_mismatches.append(ident)
        label = str(row.get("label", "")).strip()
        labels[label] += 1
        if not label or label == "__skip__":
            if label == "__skip__":
                skipped += 1
            else:
                missing_labels.append(ident)
        if label in NOTE_REQUIRED and not (
            str(row.get("note", "")).strip()
            or str(row.get("not_in_list_label", "")).strip()
        ):
            invalid_escapes.append(ident)

    expected_ids = set(expected)
    present_ids = set(ids)
    report = {
        "csv": str(csv_path.resolve()),
        "manifest": str(manifest_path.resolve()),
        "n_manifest": len(manifest),
        "n_rows": len(rows),
        "n_completed": len(rows) - skipped,
        "n_skipped": skipped,
        "label_counts": dict(sorted(labels.items())),
        "missing_manifest_ids": sorted(expected_ids - present_ids),
        "unknown_csv_ids": sorted(set(unknown_ids)),
        "duplicate_ids": sorted(set(duplicate_ids)),
        "duplicate_paths": sorted(set(duplicate_paths)),
        "path_mismatches": sorted(set(path_mismatches)),
        "missing_labels": sorted(set(missing_labels)),
        "invalid_escape_rows": sorted(set(invalid_escapes)),
    }
    # A live labeller may have written only a prefix of its manifest. That is
    # an incomplete queue, not a malformed row; keep the two states separate.
    report["integrity_ok"] = not any(
        report[key]
        for key in (
            "unknown_csv_ids", "duplicate_ids", "duplicate_paths",
            "path_mismatches", "missing_labels", "invalid_escape_rows",
        )
    )
    report["complete"] = not report["missing_manifest_ids"]
    report["ok"] = report["integrity_ok"]
    return report


def build_report(csv_paths: list[Path], manifest_paths: list[Path]) -> dict[str, Any]:
    if len(csv_paths) != len(manifest_paths) or not csv_paths:
        raise ValueError("provide an equal, non-empty number of --csv and --manifest paths")
    files = [audit_one(csv_path, manifest_path) for csv_path, manifest_path in zip(csv_paths, manifest_paths)]
    return {
        "record_type": "slo_completed_labelling_csv_integrity",
        "schema_version": "1.0.0",
        "method_version": "completed_labelling_csv_integrity_v1",
        "generated_epoch": time.time(),
        "files": files,
        "summary": {
            "n_files": len(files),
            "n_rows": sum(item["n_rows"] for item in files),
            "n_completed": sum(item["n_completed"] for item in files),
            "n_skipped": sum(item["n_skipped"] for item in files),
            "all_integrity_ok": all(item["integrity_ok"] for item in files),
            "all_complete": all(item["complete"] for item in files),
        },
        "decision": "integrity evidence only; labels are not promoted automatically",
        "safety": {
            "read_only": True,
            "labels_created": False,
            "labels_promoted_to_gold": False,
            "source_audio_modified": False,
            "rename_actions": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", dest="csv_paths", action="append", type=Path, required=True)
    parser.add_argument("--manifest", dest="manifest_paths", action="append", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true",
                        help="fail if any CSV does not contain every manifest row")
    args = parser.parse_args()
    try:
        report = build_report(args.csv_paths, args.manifest_paths)
    except (OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        raise SystemExit(f"FAIL CLOSED: {exc}") from exc
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    passed = report["summary"]["all_integrity_ok"] and (
        report["summary"]["all_complete"] or not args.require_complete
    )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
