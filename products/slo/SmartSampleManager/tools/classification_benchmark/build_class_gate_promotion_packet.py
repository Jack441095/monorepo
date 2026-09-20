#!/usr/bin/env python3
"""Build a fail-closed, review-only packet after class-gate validation.

The packet is intentionally not an approval command. It only joins complete
human validation evidence to the unseen-library candidate queue and marks
classes that may be considered for a separate explicit approval review.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any


def build_packet(queue_path: Path, validation_path: Path) -> dict[str, Any]:
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if queue.get("record_type") != "slo_class_conditional_gate_testing_review":
        raise ValueError("class-gate queue has an unexpected record type")
    if validation.get("record_type") != "slo_class_conditional_gate_validation":
        raise ValueError("validation receipt has an unexpected record type")
    summary = validation.get("summary", {})
    if int(summary.get("n_labelled", 0)) != int(summary.get("n_manifest", -1)):
        raise ValueError("FAIL CLOSED: human validation is incomplete")
    if any(not record.get("descriptive_95", False) and record.get("n", 0) >= 40
           for record in validation.get("classes", {}).values()
           if record.get("n", 0) > 0):
        # This is not an error; it simply means the class remains review-only.
        pass

    candidates = Counter(row.get("candidate_class", "") for row in queue.get("rows", []))
    classes: dict[str, Any] = {}
    for class_name, n_candidates in sorted(candidates.items()):
        evidence = validation.get("classes", {}).get(class_name)
        if evidence is None:
            raise ValueError(f"FAIL CLOSED: no validation evidence for {class_name}")
        descriptive = bool(evidence.get("descriptive_95", False))
        classes[class_name] = {
            "candidate_rows": int(n_candidates),
            "validation": evidence,
            "review_approval_candidate": descriptive,
            "auto_approved": False,
            "decision": "separate explicit review required" if descriptive else "remain review-only",
        }

    return {
        "record_type": "slo_class_gate_promotion_review_packet",
        "schema_version": "1.0.0",
        "method_version": "class_gate_promotion_review_v1",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_queue": str(queue_path.resolve()),
        "source_validation": str(validation_path.resolve()),
        "summary": {
            "n_candidates": sum(candidates.values()),
            "candidate_classes": len(classes),
            "review_approval_candidate_classes": sum(
                value["review_approval_candidate"] for value in classes.values()
            ),
        },
        "classes": classes,
        "decision": "validation evidence only; no class is approved or promoted automatically",
        "safety": {
            "read_only": True,
            "auto_approved": False,
            "production_model_changed": False,
            "rename_actions": False,
            "source_audio_modified": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        packet = build_packet(args.queue, args.validation)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"FAIL CLOSED: {exc}") from exc
    args.out.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(packet["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
