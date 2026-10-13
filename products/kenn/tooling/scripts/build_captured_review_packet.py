#!/usr/bin/env python3
"""Blind a captured answer run into a human-review packet plus a private unblinding key.

    build_captured_review_packet.py --capture CAPTURE.json --output PACKET.json --key-output KEY.json

Offline: it never imports the engine, so no retrieval or model work runs and the answers reviewed are exactly the
ones captured. It does not score anything, and a delivery verdict ("accepted") never stands in for a grade.

This lives apart from `build_human_review_packet.py` on purpose. The internal-beta gate binds the 24 Sept packet to
the sha256 of that builder, so any edit there, even an unrelated one, turns the human-review gate from pending to
fail (seen 11 Oct, when this mode was first added inside it).
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from uuid import uuid4


# The same ten criteria and release bars as build_human_review_packet.py, copied rather than imported because that
# module imports the engine at load. test_captured_review_contract.py fails if the two copies drift.
CRITERIA = (
    "intent_correctness",
    "technical_correctness",
    "evidence_use",
    "ableton_practicality",
    "uncertainty",
    "citation_support",
    "clarity",
    "completeness",
    "safety",
    "overclaiming_control",
)

RELEASE_THRESHOLDS = {
    "minimum_overall_combined_mean": 1.7,
    "minimum_critical_criterion_mean": 1.8,
    "critical_criteria": [
        "technical_correctness",
        "evidence_use",
        "safety",
        "overclaiming_control",
    ],
    "minimum_category_combined_mean": 1.5,
}


def build_captured(capture: dict) -> tuple[dict, dict]:
    """Blind every captured case without invoking retrieval or treating acceptance as a grade."""
    if capture.get("schema") != "kenn.answer_capture.v1" or not isinstance(capture.get("cases"), list) or not capture["cases"]:
        raise ValueError("Expected a non-empty kenn.answer_capture.v1 capture")
    identities = set()
    rows = []
    build_identity = capture.get("provenance")
    if not isinstance(build_identity, dict) or not build_identity:
        raise ValueError("Capture provenance is required; unknown fields may be null")
    for case in capture["cases"]:
        if not isinstance(case, dict):
            raise ValueError("Capture cases must be objects")
        identity = case.get("case_id")
        if not isinstance(identity, str):
            raise ValueError("Capture IDs must be text")
        identity = identity.strip()
        if not identity or identity in identities:
            raise ValueError("Capture IDs must be non-empty and unique")
        identities.add(identity)
        if case.get("provenance", build_identity) != build_identity:
            raise ValueError("Incompatible builds must be reviewed in separate packets")
        if not all(key in case for key in ("question", "answer", "family", "split", "delivery")):
            raise ValueError(f"Incomplete capture case {identity}")
        if any(not isinstance(case[field], str) or not case[field].strip() for field in ("question", "family", "split")) or not isinstance(case["answer"], str):
            raise ValueError("Capture question, family and split need text; missing answers remain an empty string")
        # "cancelled" (reply discarded for a newer turn) and "error" (nothing measured, e.g. the companion was
        # down) come from measure_chat_latency since 13 Oct 2026; they stay in the denominator like the rest.
        if case["delivery"] not in {"accepted", "rejected", "busy", "timeout", "not_attempted", "cancelled", "error"}:
            raise ValueError("Unknown delivery outcome")
        rows.append(case)
    if len({case["split"] for case in rows}) != 1:
        raise ValueError("Tuning, sealed, human-review and regression splits require separate packets")
    random.SystemRandom().shuffle(rows)
    packet_id = uuid4().hex
    visible, key_rows = [], []
    for position, case in enumerate(rows):
        blind_id = f"case-{position + 1:04d}"
        visible.append({
            "case_id": blind_id, "category": case["family"], "split": case["split"],
            "question": case["question"],
            "response": {"answer": case["answer"], "evidence": case.get("evidence")},
        })
        # Delivery, author history and model identity can bias a reviewer; retain them only in the key.
        key_rows.append({"case_id": blind_id, "capture": case})
    packet = {
        "schema": "kenn_chat_human_review_packet.v2", "packet_id": packet_id,
        "case_count": len(visible), "cases": visible, "criteria": list(CRITERIA),
        "release_thresholds": RELEASE_THRESHOLDS, "human_review": "pending",
        "scoring_scale": {"0": "wrong or unsupported", "1": "partial", "2": "correct and useful"},
        "outcomes_required": ["correct", "clarify", "wrong"],
    }
    key = {"schema": "kenn.human_review_key.v1", "packet_id": packet_id, "provenance": build_identity, "cases": key_rows}
    return packet, key


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capture", type=Path, required=True, help="offline kenn.answer_capture.v1 JSON")
    parser.add_argument("--output", type=Path, required=True, help="reviewer-visible blinded packet")
    parser.add_argument("--key-output", type=Path, required=True, help="private unblinding key, outside reviewer-visible files")
    args = parser.parse_args()
    if args.key_output.resolve().is_relative_to(args.output.resolve().parent):
        parser.error("--key-output must be outside the reviewer packet directory")
    packet, key = build_captured(json.loads(args.capture.read_text(encoding="utf-8")))
    if args.key_output.exists() or args.output.exists():
        parser.error("refusing to overwrite a review packet or key")
    args.key_output.parent.mkdir(parents=True, exist_ok=True)
    args.key_output.write_text(json.dumps(key, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Captured identities stay private even when a shared directory has a permissive umask.
    args.key_output.chmod(0o600)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.expanduser().resolve().write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "created", "output": str(args.output), "case_count": packet["case_count"], "human_review": packet["human_review"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
