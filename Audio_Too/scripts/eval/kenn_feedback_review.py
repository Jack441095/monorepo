#!/usr/bin/env python3
"""CLI review pass for KENN human feedback and training labels."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WEBSITE = ROOT / "business" / "app"


def _load_improvement_module():
    if str(WEBSITE) not in sys.path:
        sys.path.insert(0, str(WEBSITE))
    import llm_improvement  # noqa: E402

    return llm_improvement


def _draft_feedback_evals(llm_improvement, limit: int) -> list[dict]:
    queue = llm_improvement.improvement_queue(limit=max(1, limit))
    drafted: list[dict] = []
    for item in queue.get("items", []):
        if item.get("source") != "feedback":
            continue
        source_id = str(item.get("source_id") or "").strip()
        if not source_id:
            continue
        result = llm_improvement.draft_eval_from_feedback(source_id)
        drafted.append(
            {
                "source_id": source_id,
                "ok": bool(result.get("ok")),
                "case_id": (result.get("case") or {}).get("id", ""),
                "error": result.get("error", ""),
                "path": result.get("path", ""),
            }
        )
    return drafted


def run_review(*, export: bool = False, draft_feedback_evals: bool = False, limit: int = 12) -> dict:
    llm_improvement = _load_improvement_module()
    training = llm_improvement.training_records_snapshot(limit=500)
    queue = llm_improvement.improvement_queue(limit=limit)
    feedback = llm_improvement.demo_feedback_summary(limit=limit)
    plan = llm_improvement.repair_plan(
        feedback=feedback,
        agent_queue=queue,
        training=training,
        limit=limit,
    )
    payload: dict = {
        "ok": True,
        "training_summary": training.get("summary", {}),
        "training_diagnostics": training.get("diagnostics", {}),
        "queue_total": queue.get("total", 0),
        "queue_items": queue.get("items", []),
        "queue_covered_skipped": queue.get("covered_skipped", 0),
        "queue_fixture_skipped": queue.get("fixture_skipped", 0),
        "repair_plan": plan.get("items", []),
        "paths": {
            "training_records": training.get("path", ""),
            "review_labels": training.get("review_path", ""),
            "reviewed_export": training.get("reviewed_export_path", ""),
            "hard_negatives": training.get("hard_negatives_path", ""),
            "route_memory": training.get("route_memory_path", ""),
        },
        "exports": {},
        "drafted_eval_cases": [],
    }
    if export:
        payload["exports"] = {
            "reviewed_training": llm_improvement.export_reviewed_training(),
            "hard_negatives": llm_improvement.export_hard_negatives(),
            "route_memory": llm_improvement.export_route_memory(),
        }
    if draft_feedback_evals:
        payload["drafted_eval_cases"] = _draft_feedback_evals(llm_improvement, limit)
    return payload


def print_text(payload: dict) -> None:
    summary = payload.get("training_summary", {})
    print("KENN feedback review")
    print(
        "Training rows: "
        f"{summary.get('total', 0)} total - {summary.get('reviewed', 0)} reviewed - "
        f"{summary.get('should_fallback', 0)} should-fallback - "
        f"{summary.get('source_incorrect', 0)} source issues"
    )
    print(f"Improvement queue: {payload.get('queue_total', 0)} item(s)")
    covered_skipped = int(payload.get("queue_covered_skipped") or 0)
    if covered_skipped:
        print(f"Covered by evals: {covered_skipped} stale signal(s) skipped")
    fixture_skipped = int(payload.get("queue_fixture_skipped") or 0)
    if fixture_skipped:
        print(f"Test/demo fixtures: {fixture_skipped} signal(s) skipped")
    for item in payload.get("queue_items", [])[:5]:
        print(f"  - {item.get('question', '')} [{item.get('source', '')}:{item.get('source_id', '')}]")
    for name, result in (payload.get("exports") or {}).items():
        status = "ok" if result.get("ok") else "failed"
        count = result.get("count", result.get("summary", {}).get("shown", 0))
        print(f"Export {name}: {status} - {count}")
    drafted = payload.get("drafted_eval_cases") or []
    if drafted:
        ok = sum(1 for item in drafted if item.get("ok"))
        print(f"Drafted feedback evals: {ok}/{len(drafted)}")
    plan = payload.get("repair_plan") or []
    if plan:
        top = plan[0]
        print(f"Next repair: {top.get('title', '')}")
        print(f"Command: {top.get('command', '')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Review KENN feedback labels and export improvement artifacts.")
    parser.add_argument("--export", action="store_true", help="Write reviewed training, hard negatives, and route memory.")
    parser.add_argument(
        "--draft-feedback-evals",
        action="store_true",
        help="Draft eval cases for needs-work tester feedback in the improvement queue.",
    )
    parser.add_argument("--limit", type=int, default=12, help="Number of queue/plan items to include.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    payload = run_review(
        export=args.export,
        draft_feedback_evals=args.draft_feedback_evals,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_text(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
