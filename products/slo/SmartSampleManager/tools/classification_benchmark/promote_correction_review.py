#!/usr/bin/env python3
"""Apply explicit owner decisions to a correction review packet.

This is a governance step, not a training step. It accepts a reviewer decision
CSV and emits a promotion-candidate manifest. It never edits the source JSONL,
the corpus, model files, rename plans, or audio. Even accepted rows remain
``owner_approved_pending_rebuild`` until a separate, audited dataset-build
command consumes them.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


METHOD_VERSION = "promote_correction_review_v1"
DISPOSITIONS = {"accept", "reject", "defer"}
DECISION_FIELDS = ("correction_id", "disposition", "reviewer", "reviewer_note")


def _read_packet(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read packet: {exc}") from exc
    if payload.get("record_type") != "slo_cpp_correction_review_packet":
        raise ValueError("packet is not an SLO C++ correction review packet")
    if payload.get("safety", {}).get("automatic_promotion") is not False:
        raise ValueError("packet safety receipt does not prove automatic promotion is disabled")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("packet contains no rows")
    ids = [row.get("correction_id") for row in rows]
    if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("packet correction IDs must be unique non-empty strings")
    return payload


def _read_decisions(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        raise ValueError(f"decision CSV does not exist: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [field for field in DECISION_FIELDS if field not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"decision CSV missing fields: {', '.join(missing)}")
        decisions: dict[str, dict[str, str]] = {}
        for line_number, row in enumerate(reader, 2):
            correction_id = (row.get("correction_id") or "").strip()
            disposition = (row.get("disposition") or "").strip().lower()
            reviewer = (row.get("reviewer") or "").strip()
            note = (row.get("reviewer_note") or "").strip()
            if not correction_id:
                raise ValueError(f"decision row {line_number} has no correction_id")
            if correction_id in decisions:
                raise ValueError(f"duplicate correction_id in decisions: {correction_id}")
            if disposition not in DISPOSITIONS:
                raise ValueError(f"unsupported disposition at row {line_number}: {disposition}")
            if not reviewer:
                raise ValueError(f"reviewer is required at row {line_number}")
            if disposition in {"reject", "defer"} and not note:
                raise ValueError(f"reviewer_note is required for {disposition} at row {line_number}")
            decisions[correction_id] = {
                "correction_id": correction_id,
                "disposition": disposition,
                "reviewer": reviewer,
                "reviewer_note": note,
            }
    if not decisions:
        raise ValueError("decision CSV is empty")
    return decisions


def _write_new(path: Path, value: str) -> None:
    if path.exists():
        raise ValueError(f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def promote(packet_path: Path, decisions_path: Path, output_dir: Path) -> dict[str, Any]:
    packet = _read_packet(packet_path)
    decisions = _read_decisions(decisions_path)
    rows = packet["rows"]
    by_id = {row["correction_id"]: row for row in rows}
    unknown = sorted(set(decisions) - set(by_id))
    if unknown:
        raise ValueError(f"decision references unknown correction IDs: {', '.join(unknown)}")
    missing = sorted(set(by_id) - set(decisions))
    if missing:
        raise ValueError(f"decision CSV must account for every packet row; missing {len(missing)} IDs")

    output_rows = []
    for row in rows:
        decision = decisions[row["correction_id"]]
        output_rows.append({
            **row,
            "reviewer": decision["reviewer"],
            "reviewer_note": decision["reviewer_note"],
            "review_disposition": decision["disposition"],
            "promotion_status": (
                "owner_approved_pending_rebuild" if decision["disposition"] == "accept"
                else "owner_rejected" if decision["disposition"] == "reject"
                else "deferred"
            ),
        })

    output_dir = output_dir.resolve()
    manifest_path = output_dir / "correction_promotion_candidates.jsonl"
    receipt_path = output_dir / "correction_promotion_receipt.json"
    lines = [json.dumps({
        "record_type": "slo_correction_promotion_candidate_manifest",
        "schema_version": "1.0.0",
        "method_version": METHOD_VERSION,
        "source_packet": str(packet_path.resolve()),
        "source_packet_sha256": hashlib.sha256(packet_path.read_bytes()).hexdigest(),
        "source_decisions_sha256": hashlib.sha256(decisions_path.read_bytes()).hexdigest(),
        "n_rows": len(output_rows),
        "safety": {
            "source_packet_modified": False,
            "training_ground_truth_changed": False,
            "model_changed": False,
            "rename_actions": False,
            "audio_modified": False,
        },
    }, sort_keys=True)]
    lines.extend(json.dumps(row, sort_keys=True) for row in output_rows)
    receipt = {
        "record_type": "slo_correction_promotion_receipt",
        "schema_version": "1.0.0",
        "method_version": METHOD_VERSION,
        "source_packet": str(packet_path.resolve()),
        "source_decisions": str(decisions_path.resolve()),
        "counts": {
            disposition: sum(row["review_disposition"] == disposition for row in output_rows)
            for disposition in sorted(DISPOSITIONS)
        },
        "decision": "OWNER_APPROVAL_RECORDED; DATASET_REBUILD_REQUIRED",
        "safety": {
            "training_ground_truth_changed": False,
            "automatic_promotion": False,
            "rename_actions": False,
            "audio_modified": False,
        },
    }
    _write_new(manifest_path, "\n".join(lines) + "\n")
    _write_new(receipt_path, json.dumps(receipt, indent=2) + "\n")
    return {
        "status": "OWNER_DECISIONS_RECORDED",
        "manifest": str(manifest_path),
        "receipt": str(receipt_path),
        "counts": receipt["counts"],
        "training_ground_truth_changed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = promote(args.packet, args.decisions, args.output_dir)
    except ValueError as exc:
        print(f"FAIL CLOSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
