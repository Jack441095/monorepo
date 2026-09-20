#!/usr/bin/env python3
"""Build an advisory calibration report for fused classifier decisions.

Reviewer feedback is joined to the immutable fused-decision packet by path and
packet hash. Accepted candidates are hits; corrected or rejected candidates are
misses. The report never promotes labels or grants automatic action.
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


VERSION = "label_free_decision_calibration_v1"
DECISION_EVENTS = {"accept_fused_candidate", "correct_fused_candidate", "reject_fused_candidate"}


def _feedback_module():
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
    rows: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows", []):
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("packet row has no path")
        path = str(Path(row["path"]).resolve())
        if path in rows:
            raise ValueError(f"duplicate packet path: {row['path']}")
        if row.get("semantic_label") is not None:
            raise ValueError("packet contains a semantic label")
        rows[path] = row
    return payload, rows


def _wilson(hits: int, n: int, z: float = 1.959963984540054) -> float | None:
    if n <= 0:
        return None
    p = hits / n
    den = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    spread = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n)
    return max(0.0, (centre - spread) / den)


def _stats(rows: list[tuple[dict[str, Any], bool]], target: float, minimum: int) -> dict[str, Any]:
    n = len(rows)
    hits = sum(accepted for _, accepted in rows)
    lower = _wilson(hits, n)
    return {
        "n_reviewed": n,
        "n_accepted": hits,
        "n_rejected_or_corrected": n - hits,
        "observed_precision": round(hits / n, 6) if n else None,
        "wilson_lower_95": round(lower, 6) if lower is not None else None,
        "target_precision": target,
        "minimum_reviews": minimum,
        "promotion_candidate": bool(n >= minimum and lower is not None and lower >= target),
    }


def build(packet: Path, feedback: Path, out: Path,
          target_precision: float = 0.95, min_reviews: int = 30) -> dict[str, Any]:
    if not 0.0 < target_precision <= 1.0 or min_reviews < 1:
        raise ValueError("invalid calibration thresholds")
    payload, packet_rows = _read_packet(packet)
    packet_sha = hashlib.sha256(packet.read_bytes()).hexdigest()
    feedback_module = _feedback_module()
    events = [event for event in feedback_module.read_events(feedback)
              if event.get("event_type") in DECISION_EVENTS]
    by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        path = str(Path(event["path"]).resolve())
        if path not in packet_rows:
            raise ValueError(f"fused feedback path is not in packet: {event['path']}")
        if event.get("source_packet_sha256") != packet_sha:
            raise ValueError(f"feedback packet hash does not match packet: {event['path']}")
        fused = packet_rows[path].get("fused_decision")
        if not isinstance(fused, dict):
            raise ValueError(f"packet path has no fused decision: {event['path']}")
        expected = fused.get("candidate_label") or fused.get("domain_candidate_label")
        if not isinstance(expected, str) or not expected:
            raise ValueError(f"packet path has no candidate: {event['path']}")
        if event.get("candidate_label") != expected:
            raise ValueError(f"feedback candidate does not match packet: {event['path']}")
        by_path[path].append(event)

    adjudicated: list[tuple[dict[str, Any], bool]] = []
    rereviewed = 0
    for path, path_events in by_path.items():
        rereviewed += max(0, len(path_events) - 1)
        adjudicated.append((packet_rows[path], path_events[-1]["event_type"] == "accept_fused_candidate"))

    slices: dict[str, list[tuple[dict[str, Any], bool]]] = defaultdict(list)
    for row, accepted in adjudicated:
        fused = row.get("fused_decision") or {}
        domain = str(fused.get("domain") or "unknown_or_mixture")
        scope = str(fused.get("candidate_scope") or "none")
        slices[domain].append((row, accepted))
        slices[f"scope:{scope}"].append((row, accepted))
    slices["all"] = adjudicated
    reports = {name: _stats(rows, target_precision, min_reviews)
               for name, rows in sorted(slices.items())}
    qualified = [name for name, stats in reports.items()
                 if name != "all" and stats["promotion_candidate"]]
    result = {
        "record_type": "slo_label_free_decision_calibration",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_packet": str(packet.resolve()),
        "source_packet_sha256": packet_sha,
        "source_feedback": str(feedback.resolve()),
        "source_feedback_sha256": hashlib.sha256(feedback.read_bytes()).hexdigest(),
        "n_packet_rows": len(packet_rows),
        "n_decision_events": len(events),
        "n_adjudicated_paths": len(adjudicated),
        "n_re_reviewed_paths": rereviewed,
        "slices": reports,
        "promotion_candidate_slices": qualified,
        "calibration_kind": "reviewer_fused_decision_wilson_lower_bound",
        "accuracy_claim": None,
        "auto_action_allowed": False,
        "safety": {
            "read_only": True,
            "ground_truth_read": True,
            "semantic_labels_created": False,
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
    result = build(args.packet, args.feedback, args.out, args.target_precision, args.min_reviews)
    print(json.dumps({"out": str(args.out), "n_adjudicated_paths": result["n_adjudicated_paths"],
                      "promotion_candidate_slices": result["promotion_candidate_slices"],
                      "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
