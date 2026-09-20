#!/usr/bin/env python3
"""Evaluate KENN's evidence-only Arrangement and Session View advice.

The corpus is synthetic and sealed in this source file: it contains no user
set names, audio, or Live connection.  It verifies structural evidence,
advisory-only output, and abstention rather than musical taste.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))

from kenn.core.arrangement_analysis import SCHEMA, SUGGESTIONS_SCHEMA, analyze_arrangement_context  # noqa: E402
from kenn.core.session_context import build_session_context  # noqa: E402


EVALUATION_SCHEMA = "kenn.arrangement_intelligence_evaluation.v1"


def _timeline_only_context() -> dict[str, Any]:
    return build_session_context(snapshot={
        "status": "connected",
        "tracks": [
            {"index": 0, "name": "Kick", "arrangement_clips": [
                {"index": 0, "name": "Kick Intro", "start_time_beats": 1.0, "length_beats": 64.0},
            ]},
            {"index": 1, "name": "Bass", "arrangement_clips": [
                {"index": 0, "name": "Bass Drop", "start_time_beats": 33.0, "length_beats": 32.0},
            ]},
        ],
        "scenes": [],
        "locators": [
            {"index": 0, "name": "Intro", "time_beats": 1.0},
            {"index": 1, "name": "Drop", "time_beats": 33.0},
        ],
    })


def _session_view_context() -> dict[str, Any]:
    return build_session_context(snapshot={
        "status": "connected",
        "tracks": [
            {"index": 0, "name": "Kick", "clip_slots": [
                {"index": 0, "name": "Kick Verse", "has_clip": True},
                {"index": 1, "name": "Kick Drop", "has_clip": True},
            ]},
            {"index": 1, "name": "Bass", "clip_slots": [
                {"index": 1, "name": "Bass Drop", "has_clip": True},
            ]},
        ],
        "scenes": [{"index": 0, "name": "Verse"}, {"index": 1, "name": "Drop"}],
    })


CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "arrangement_only_density_lift",
        "category": "arrangement_view",
        "context": _timeline_only_context(),
        "expect": {"status": "current", "suggestion_title_contains": "timeline density lift", "timeline_transition": "timeline_density_lift"},
    },
    {
        "id": "session_view_density_lift",
        "category": "session_view",
        "context": _session_view_context(),
        "expect": {"status": "current", "suggestion_title_contains": "density lift", "transition": "density_lift"},
    },
    {
        "id": "no_structural_evidence_abstains",
        "category": "abstention",
        "context": build_session_context(snapshot={"status": "connected", "tracks": [], "scenes": [], "locators": []}),
        "expect": {"status": "current", "suggestion_count": 0},
    },
    {
        "id": "stale_context_fails_closed",
        "category": "safety",
        "context": {**_timeline_only_context(), "observed_at": 0.0},
        "expect": {"status": "unavailable", "suggestion_count": 0},
    },
)


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    analysis = analyze_arrangement_context(case["context"])
    expect = case["expect"]
    suggestions = [item for item in (analysis.get("suggestions") or []) if isinstance(item, dict)]
    failures: list[str] = []
    if analysis.get("schema") != SCHEMA:
        failures.append("schema")
    if analysis.get("status") != expect["status"]:
        failures.append("status")
    if analysis.get("advisory_only") is not True or analysis.get("mutation_authorized") is not False:
        failures.append("analysis_mutation_boundary")
    if "suggestion_count" in expect and len(suggestions) != expect["suggestion_count"]:
        failures.append("suggestion_count")
    if expect.get("transition") not in {None, *(item.get("candidate") for item in analysis.get("transitions") or [] if isinstance(item, dict))}:
        failures.append("session_transition")
    if expect.get("timeline_transition") not in {None, *(item.get("candidate") for item in analysis.get("timeline_transitions") or [] if isinstance(item, dict))}:
        failures.append("timeline_transition")
    required_title = str(expect.get("suggestion_title_contains") or "").lower()
    if required_title and not any(required_title in str(item.get("title") or "").lower() for item in suggestions):
        failures.append("suggestion_missing")
    for suggestion in suggestions:
        if suggestion.get("schema") != SUGGESTIONS_SCHEMA:
            failures.append("suggestion_schema")
        if suggestion.get("advisory_only") is not True or suggestion.get("live_mutation_authorized") is not False:
            failures.append("suggestion_mutation_boundary")
        if suggestion.get("evidence", {}).get("evidence_class") != "observed_session_fact":
            failures.append("suggestion_evidence")
    return {
        "id": case["id"], "category": case["category"], "passed": not failures,
        "status": analysis.get("status"), "suggestion_count": len(suggestions), "failures": sorted(set(failures)),
    }


def evaluate() -> dict[str, Any]:
    rows = [evaluate_case(case) for case in CASES]
    return {
        "schema": EVALUATION_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(rows),
        "passed_case_count": sum(bool(row["passed"]) for row in rows),
        "all_cases_passed": bool(rows) and all(bool(row["passed"]) for row in rows),
        "execution_authorized": False,
        "rows": rows,
        "limitations": [
            "Synthetic structural cases validate evidence, abstention, and mutation boundaries; they do not establish musical quality or producer preference.",
            "This evaluator never opens OSC, connects to Live, or reads a user session.",
        ],
    }


def main() -> int:
    report = evaluate()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_cases_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
