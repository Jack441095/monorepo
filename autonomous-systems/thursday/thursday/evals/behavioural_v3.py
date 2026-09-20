"""THURSDAY_BEHAVIOURAL_V3 — deterministic company intelligence qualification.

Evaluates the Thursday V2-C deterministic company intelligence engine using
the 200+ generated scenarios from V2, executing the queries directly through
the candidate deterministic handlers rather than raw LLM generation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from unittest.mock import patch

from thursday.evals.behavioural import OllamaProvider, OpenAICompatProvider
from thursday.evals.behavioural_v2 import (
    SynthState,
    build_split_views,
    SCORERS,
    _split,
)
from thursday.company_state import CompanySnapshot, TaskView, GoalView, ApprovalView, AgentRunView
from thursday.registry.handlers import _handle_company_state

def synth_to_snapshot(st: SynthState) -> CompanySnapshot:
    goals = [
        GoalView(goal_id=g["goal_id"], kind="standard", title=g["title"], status=g["status"], progress=g["progress"], target_date_epoch=None)
        for g in st.goals
    ]
    
    overdue_tasks = []
    blocked_tasks = []
    due_today_tasks = []
    for t in st.tasks:
        view = TaskView(
            task_id=t["task_id"],
            title=t["title"],
            project_id=t["project_id"],
            status=t["status"],
            priority=t["priority"],
            due_epoch=time.time() - 3600 if t.get("overdue") else (time.time() if t.get("due_today") else None),
            blocked_by=tuple(t.get("blocked_by") or [])
        )
        if t.get("overdue"):
            overdue_tasks.append(view)
        if t["status"] == "blocked" or t.get("blocked_by"):
            blocked_tasks.append(view)
        if t.get("due_today"):
            due_today_tasks.append(view)
            
    pending_approvals = [
        ApprovalView(
            approval_id=a["approval_id"],
            capability_id="cap",
            summary=a["summary"],
            action_level=a["action_level"],
            reversibility="reversible",
            created_at_epoch=time.time()
        )
        for a in st.approvals
    ]
    
    failed_agent_runs = []
    recent_agent_runs = []
    for r in st.agent_runs:
        run_view = AgentRunView(
            run_id=f"run-{r['agent_id']}",
            agent_id=r["agent_id"],
            status=r["status"],
            blocker=r.get("blocker"),
            started_at_epoch=time.time() - 3600,
            finished_at_epoch=time.time()
        )
        if r["status"] == "failed":
            failed_agent_runs.append(run_view)
        recent_agent_runs.append(run_view)
        
    all_tasks_list = []
    for t in st.tasks:
        view = TaskView(
            task_id=t["task_id"],
            title=t["title"],
            project_id=t["project_id"],
            status=t["status"],
            priority=t["priority"],
            due_epoch=time.time() - 3600 if t.get("overdue") else (time.time() if t.get("due_today") else None),
            blocked_by=tuple(t.get("blocked_by") or [])
        )
        all_tasks_list.append(view)

    snap = CompanySnapshot(
        captured_at_epoch=time.time(),
        goals=tuple(goals),
        overdue_tasks=tuple(overdue_tasks),
        blocked_tasks=tuple(blocked_tasks),
        due_today_tasks=tuple(due_today_tasks),
        active_projects=st.projects,
        risks=st.risks,
        open_decisions=[],
        pending_approvals=tuple(pending_approvals),
        recent_agent_runs=tuple(recent_agent_runs),
        failed_agent_runs=tuple(failed_agent_runs)
    )
    object.__setattr__(snap, "_all_tasks", tuple(all_tasks_list))
    return snap


def run(split_filter=None) -> dict[str, Any]:
    if split_filter is None:
        split_filter = ("DEV", "CALIBRATION")
        
    views = build_split_views()
    selected = [c for s in split_filter for c in views[s]]
    records = []
    passed = 0
    latencies = []
    
    for case in selected:
        snapshot = synth_to_snapshot(case.state)
        
        t0 = time.perf_counter()
        # Mock get_snapshot to return our synthetic snapshot
        with patch("thursday.company_state.get_snapshot", return_value=snapshot):
            response = _handle_company_state(case.question, {})
        latency = time.perf_counter() - t0
        latencies.append(latency)
        
        result = SCORERS[case.scorer](case, response)
        result.update({
            "case_id": case.case_id,
            "category": case.category,
            "difficulty": case.difficulty,
            "split": _split(case.case_id),
            "latency_s": round(latency, 3),
        })
        if not result["passed"]:
            print(f"\n[FAIL] {case.case_id} ({case.category})")
            print(f"  Q: {case.question}")
            print(f"  A: {response}")
            print(f"  Score: {result}")
        records.append(result)
        passed += bool(result["passed"])

    total = len(records)
    def rate(pred):
        return round(sum(1 for r in records if pred(r)) / total, 4) if total else 0.0

    enum_records = [r for r in records if r["category"] == "enumeration"]

    summary = {
        "schema": "thursday.behavioural_v3.v1",
        "splits_evaluated": list(split_filter),
        "total_cases": total,
        "passed": passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "by_difficulty": {
            d: {
                "cases": sum(1 for r in records if r["difficulty"] == d),
                "pass_rate": round(
                    sum(1 for r in records if r["difficulty"] == d and r["passed"])
                    / max(1, sum(1 for r in records if r["difficulty"] == d)), 4),
            }
            for d in ("EASY", "NORMAL", "HARD", "ADVERSARIAL")
        },
        "by_category": {
            cat: round(sum(1 for r in records if r["category"] == cat and r["passed"])
                       / max(1, sum(1 for r in records if r["category"] == cat)), 4)
            for cat in sorted({r["category"] for r in records})
        },
        "priority_accuracy": round(
            sum(1 for r in records if r["category"] == "priority" and r["passed"])
            / max(1, sum(1 for r in records if r["category"] == "priority")), 4),
        "enumeration_completeness_avg": round(statistics.mean(
            [r.get("completeness", 1.0) for r in enum_records]), 4) if enum_records else None,
        "unsupported_claim_rate": rate(lambda r: r.get("forbidden_found")),
        "median_latency_s": round(statistics.median(latencies), 3) if latencies else None,
    }
    return {"summary": summary, "records": records}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path", default="")
    parser.add_argument("--holdout", action="store_true",
                        help="include the frozen holdout split")
    args = parser.parse_args(argv)

    splits = ("DEV", "CALIBRATION", "HOLDOUT") if args.holdout else ("DEV", "CALIBRATION")
    report = run(splits)
    print(json.dumps(report["summary"], indent=2))
    
    if args.json_path:
        with open(args.json_path, "w") as fh:
            json.dump(report, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
