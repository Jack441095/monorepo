#!/usr/bin/env python3
"""Build a breadth-first, duplicate-free validation manifest for class gates."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

SD = Path(__file__).resolve().parent


def load_excluded_paths(path: Path | None) -> set[str]:
    """Return absolute paths already used by an earlier validation batch."""
    if path is None:
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("items", payload.get("rows", []))
    else:
        raise ValueError("excluded manifest must be a list or object")
    if not isinstance(items, list):
        raise ValueError("excluded manifest items must be an array")
    return {str(row["path"]).strip() for row in items
            if isinstance(row, dict) and row.get("path")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", type=Path,
                    default=SD / "class_conditional_gate_testing_review_v1.csv")
    ap.add_argument("--out", type=Path,
                    default=SD / "class_conditional_gate_validation_manifest_v1.json")
    ap.add_argument("--exclude-manifest", type=Path,
                    help="previous validation manifest/receipt whose paths must not be reused")
    ap.add_argument("--per-class", type=int, default=40)
    args = ap.parse_args()

    rows = list(csv.DictReader(args.queue.open(encoding="utf-8")))
    excluded_paths = load_excluded_paths(args.exclude_manifest)
    spec = importlib.util.spec_from_file_location("slo_inventory", SD / "sample_library_inventory.py")
    inventory = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(inventory)
    eligible = [r for r in rows
                if not r.get("exact_duplicate_group") and
                not r.get("near_duplicate_group") and
                str(r.get("path", "")).strip() not in excluded_paths]
    for row in eligible:
        if not row.get("vendor"):
            row["vendor"] = inventory.attribute(row["path"])[1]
    by_class_vendor: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for row in eligible:
        by_class_vendor[row["candidate_class"]][row["vendor"]].append(row)

    selected: list[dict[str, str]] = []
    selected_summary: dict[str, dict[str, int]] = {}
    for cls in sorted(by_class_vendor):
        vendors = by_class_vendor[cls]
        for values in vendors.values():
            values.sort(key=lambda r: r["path"])
        chosen: list[dict[str, str]] = []
        vendor_names = sorted(vendors)
        cursor = 0
        while len(chosen) < args.per_class and vendor_names:
            vendor = vendor_names[cursor % len(vendor_names)]
            if vendors[vendor]:
                chosen.append(vendors[vendor].pop(0))
            vendor_names = [v for v in vendor_names if vendors[v]]
            if vendor_names:
                cursor = (cursor + 1) % len(vendor_names)
        selected_summary[cls] = {
            "requested": args.per_class,
            "selected": len(chosen),
            "vendors": len({r["vendor"] for r in chosen}),
        }
        selected.extend(chosen)

    selected.sort(key=lambda r: (r["candidate_class"], r["path"]))
    manifest = []
    for index, row in enumerate(selected):
        manifest.append({
            "id": index,
            "path": row["path"],
            "hint": (
                f"research candidate: {row['candidate_class']} | "
                f"confidence {float(row['confidence']):.3f} | "
                "label what you hear; do not trust the candidate"
            ),
            "candidate_class": row["candidate_class"],
            "candidate_confidence": float(row["confidence"]),
            "candidate_similarity": float(row["similarity"]),
            "vendor": row["vendor"],
            "exact_duplicate_excluded": True,
            "near_duplicate_excluded": True,
        })
    payload = {
        "record_type": "slo_class_conditional_gate_validation_manifest",
        "schema_version": "1.0.0",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "labels_created": False, "rename_actions": False},
        "source_queue": str(args.queue.resolve()),
        "selection": {
            "strategy": "round-robin by vendor within each candidate class",
            "per_class_target": args.per_class,
            "duplicate_exclusion": "exact content and conservative acoustic near-duplicate groups",
        },
        "summary": {"n_queue_rows": len(rows), "n_eligible": len(eligible),
                    "n_selected": len(manifest), "n_excluded_previous": len(excluded_paths),
                    "by_class": selected_summary},
        "excluded_previous_manifest": str(args.exclude_manifest.resolve())
            if args.exclude_manifest else None,
        "items": manifest,
    }
    args.out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    receipt = args.out.with_name(args.out.stem + "_receipt.json")
    receipt.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    print(f"wrote {args.out}")
    print(f"wrote {receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
