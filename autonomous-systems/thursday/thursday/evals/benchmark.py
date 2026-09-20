"""Run Thursday's deterministic held-out routing release gate."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from thursday.evals.corpus import (
    RoutingCase,
    final_release_holdout_cases,
    held_out_cases,
)
from thursday.orchestrator import classify_request, normalize_request_text

MIN_OVERALL_ACCURACY = 0.97
MIN_CRITICAL_ACCURACY = 0.99
MIN_TARGET_ACCURACY = 0.99


def evaluate_case(case: RoutingCase) -> dict:
    session = {
        "session_id": f"eval-{case.case_id}",
        "context": {},
        "turns": [],
    }
    if case.previous_intent:
        session["turns"].append(
            {"role": "user", "text": "prior turn", "intent": case.previous_intent}
        )
    normalized = normalize_request_text(case.text, profile_id="benchmark")
    decision = classify_request(normalized, session)
    return {
        **asdict(case),
        "normalized_text": normalized,
        "actual_intent": decision.intent.name,
        "actual_target": decision.execution_target,
        "intent_correct": decision.intent.name == case.expected_intent,
        "target_correct": decision.execution_target == case.expected_target,
        "confidence": round(float(decision.intent.confidence), 4),
    }


def evaluate(cases: list[RoutingCase] | None = None) -> tuple[dict, list[dict]]:
    records = [evaluate_case(case) for case in (cases or final_release_holdout_cases())]
    critical = [record for record in records if record["critical"]]
    overall_accuracy = sum(record["intent_correct"] for record in records) / len(records)
    critical_accuracy = sum(record["intent_correct"] for record in critical) / max(
        1, len(critical)
    )
    target_accuracy = sum(record["target_correct"] for record in records) / len(records)
    summary = {
        "schema": "thursday.routing_benchmark.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(records),
        "critical_cases": len(critical),
        "overall_accuracy": round(overall_accuracy, 4),
        "critical_accuracy": round(critical_accuracy, 4),
        "target_accuracy": round(target_accuracy, 4),
        "thresholds": {
            "overall_accuracy": MIN_OVERALL_ACCURACY,
            "critical_accuracy": MIN_CRITICAL_ACCURACY,
            "target_accuracy": MIN_TARGET_ACCURACY,
        },
    }
    summary["passed"] = (
        overall_accuracy >= MIN_OVERALL_ACCURACY
        and critical_accuracy >= MIN_CRITICAL_ACCURACY
        and target_accuracy >= MIN_TARGET_ACCURACY
    )
    summary["failure_count"] = sum(
        not (record["intent_correct"] and record["target_correct"])
        for record in records
    )
    return summary, records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--failures", action="store_true")
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    summary, records = evaluate(held_out_cases() if args.development else None)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps({"summary": summary, "records": records}, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(summary, indent=2))
    if args.failures:
        for record in records:
            if not record["intent_correct"] or not record["target_correct"]:
                print(
                    f"{record['case_id']}: {record['text']!r} expected "
                    f"{record['expected_intent']}/{record['expected_target']} got "
                    f"{record['actual_intent']}/{record['actual_target']}"
                )
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
