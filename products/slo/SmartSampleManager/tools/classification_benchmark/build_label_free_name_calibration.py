#!/usr/bin/env python3
"""Build a conservative calibration report from reviewed name candidates.

The report joins an evidence packet with the append-only feedback ledger.  It
does not create labels, modify audio, or grant rename permission.  An accepted
candidate is treated as a reviewer-confirmed hit; corrected/rejected
candidates are misses.  Wilson lower bounds are used so a small, lucky sample
cannot qualify a slice for automation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


VERSION = "label_free_name_calibration_v1"
NAME_EVENTS = {"accept_name_candidate", "correct_name_candidate", "reject_name_candidate"}


def _load_feedback_module():
    path = Path(__file__).with_name("review_feedback_events.py")
    spec = importlib.util.spec_from_file_location("review_feedback_events", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load feedback event contract")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_packet(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("record_type") != "slo_label_free_evidence_packet":
        raise ValueError("packet is not a label-free evidence packet")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("source_audio_modified")):
        raise ValueError("packet is not read-only")
    result: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows", []):
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("packet row has no path")
        if row.get("semantic_label") is not None:
            raise ValueError("packet contains a semantic label")
        path_value = row["path"]
        if not path_value.startswith("/") or path_value in result:
            raise ValueError("packet paths must be absolute and unique")
        result[path_value] = row
    return payload, result


def _wilson_lower(hits: int, n: int, z: float = 1.959963984540054) -> float | None:
    if n <= 0:
        return None
    p = hits / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    spread = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n)
    return max(0.0, (centre - spread) / denom)


def _slice_stats(rows: list[tuple[dict[str, Any], bool]], target: float,
                 min_reviews: int) -> dict[str, Any]:
    n = len(rows)
    hits = sum(1 for _, accepted in rows if accepted)
    precision = hits / n if n else None
    lower = _wilson_lower(hits, n)
    qualified = bool(n >= min_reviews and lower is not None and lower >= target)
    return {
        "n_reviewed": n,
        "n_accepted": hits,
        "n_rejected_or_corrected": n - hits,
        "observed_precision": round(precision, 6) if precision is not None else None,
        "wilson_lower_95": round(lower, 6) if lower is not None else None,
        "target_precision": target,
        "minimum_reviews": min_reviews,
        "promotion_candidate": qualified,
    }


def build(packet: Path, feedback: Path, out: Path,
          target_precision: float = 0.95, min_reviews: int = 30) -> dict[str, Any]:
    if not 0.0 < target_precision <= 1.0 or min_reviews < 1:
        raise ValueError("invalid calibration thresholds")
    payload, packet_rows = _read_packet(packet)
    packet_sha256 = hashlib.sha256(packet.read_bytes()).hexdigest()
    feedback_module = _load_feedback_module()
    events = [event for event in feedback_module.read_events(feedback)
              if event.get("event_type") in NAME_EVENTS]

    by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        path = event["path"]
        if path not in packet_rows:
            raise ValueError(f"name feedback path is not in packet: {path}")
        candidate = packet_rows[path].get("name_candidate")
        expected = candidate.get("candidate_filename") if isinstance(candidate, dict) else None
        if not isinstance(expected, str) or not expected:
            raise ValueError(f"name feedback path has no candidate: {path}")
        if event.get("candidate_filename") != expected:
            raise ValueError(f"feedback candidate does not match packet: {path}")
        if event.get("source_packet_sha256") != packet_sha256:
            raise ValueError(f"feedback packet hash does not match packet: {path}")
        by_path[path].append(event)

    # Use the latest event per path as the adjudication.  Re-review history is
    # retained in the ledger but must not inflate the denominator.
    adjudicated: list[tuple[dict[str, Any], bool]] = []
    duplicate_paths = 0
    for path, path_events in by_path.items():
        if len(path_events) > 1:
            duplicate_paths += 1
        event = path_events[-1]
        adjudicated.append((packet_rows[path], event["event_type"] == "accept_name_candidate"))

    slices: dict[str, list[tuple[dict[str, Any], bool]]] = defaultdict(list)
    for row, accepted in adjudicated:
        route = row.get("domain_route") or {}
        domain = route.get("domain_suggestion") if isinstance(route, dict) else None
        slices[str(domain or "unknown_or_mixture")].append((row, accepted))
    slices["all"] = adjudicated

    report_slices = {name: _slice_stats(rows, target_precision, min_reviews)
                     for name, rows in sorted(slices.items())}
    qualified = [name for name, stats in report_slices.items()
                 if name != "all" and stats["promotion_candidate"]]
    result = {
        "record_type": "slo_label_free_name_calibration",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_packet": str(packet.resolve()),
        "source_packet_sha256": packet_sha256,
        "source_feedback": str(feedback.resolve()),
        "source_feedback_sha256": hashlib.sha256(feedback.read_bytes()).hexdigest(),
        "n_packet_rows": len(packet_rows),
        "n_name_events": len(events),
        "n_adjudicated_paths": len(adjudicated),
        "n_re_reviewed_paths": duplicate_paths,
        "slices": report_slices,
        "promotion_candidate_slices": qualified,
        "calibration_kind": "reviewer_decision_evidence_wilson_lower_bound",
        "accuracy_claim": None,
        "auto_action_allowed": False,
        "safety": {
            "read_only": True,
            "semantic_labels_created": False,
            "ground_truth_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "automatic_promotion": False,
            "human_approval_required": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--feedback", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--target-precision", type=float, default=0.95)
    parser.add_argument("--min-reviews", type=int, default=30)
    args = parser.parse_args()
    result = build(args.packet, args.feedback, args.out,
                   args.target_precision, args.min_reviews)
    print(json.dumps({"out": str(args.out),
                      "n_adjudicated_paths": result["n_adjudicated_paths"],
                      "promotion_candidate_slices": result["promotion_candidate_slices"],
                      "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
