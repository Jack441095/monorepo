#!/usr/bin/env python3
"""Build a read-only physical-evidence packet for held taxonomy-gap labels."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from pathlib import Path

SD = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--held", type=Path, default=SD / "verified_granularity_HELD.csv")
    ap.add_argument("--out", type=Path, default=SD / "results_taxonomy_gap_review_packet_v1.json")
    args = ap.parse_args()
    rows = list(csv.DictReader(args.held.open(encoding="utf-8")))
    if not rows:
        raise SystemExit("FAIL CLOSED: held taxonomy-gap list is empty")
    spec = importlib.util.spec_from_file_location("slo_audio_definition_card", SD / "audio_definition_card.py")
    cards_mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(cards_mod)
    packet = []
    errors = []
    for row in rows:
        try:
            card = cards_mod.analyse_file(row["path"])
            packet.append({
                "id": row.get("id"),
                "path": row["path"],
                "held_label": row.get("label"),
                "note": row.get("note"),
                "not_in_list_label": row.get("not_in_list_label"),
                "collection": row.get("collection"),
                "pack": row.get("pack"),
                "definition_card": card,
            })
        except Exception as exc:
            errors.append({"path": row["path"], "error": str(exc)})
    if errors:
        raise SystemExit(f"FAIL CLOSED: {len(errors)} taxonomy-gap audio cards failed")
    counts = {}
    for row in packet:
        label = row["held_label"] or "unspecified"
        counts[label] = counts.get(label, 0) + 1
    payload = {
        "record_type": "slo_taxonomy_gap_review_packet",
        "schema_version": "1.0.0",
        "method_version": "taxonomy_gap_review_packet_v1",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "semantic_labels_created": False, "production_ground_truth_changed": False,
                   "rename_actions": False},
        "source_held_csv": str(args.held.resolve()),
        "summary": {"n_held": len(rows), "n_cards": len(packet), "n_errors": len(errors),
                    "held_labels": counts},
        "decision": "owner review required; held labels are not integrated into training",
        "rows": packet,
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
