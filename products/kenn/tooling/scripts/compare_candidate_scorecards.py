#!/usr/bin/env python3
"""Compare durable automated and intelligence receipts across two git revisions.

This is a release-engineering aid, not a substitute for the external Ableton,
human-review, or supervised-pilot evidence gates.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from typing import Any


RECEIPTS = {
    "automated_suite": "evaluation/results/KENN_AUTOMATED_SUITE_QUALIFICATION.json",
    "intelligence": "evaluation/results/KENN_INTELLIGENCE_QUALIFICATION.json",
}


def _receipt(revision: str, path: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["git", "show", f"{revision}:{path}"], check=True, capture_output=True, text=True
    )
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError(f"{revision}:{path} must be a JSON object")
    return value


def _ratio(details: str, label: str) -> float | None:
    matched = re.search(rf"{re.escape(label)}\s+(\d+)/(\d+)", details)
    if not matched or int(matched.group(2)) == 0:
        return None
    return int(matched.group(1)) / int(matched.group(2))


def summarize(receipts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    suite = receipts["automated_suite"]
    intelligence = receipts["intelligence"]
    suite_summary = str(suite.get("summary") or "")
    match = re.search(r"(\d+) passed", suite_summary)
    details = str(intelligence.get("details") or "")
    recall_match = re.search(r"hybrid recall@4\s+([0-9.]+)", details)
    return {
        "suite_passed": bool(suite.get("passed")),
        "suite_pass_count": int(match.group(1)) if match else None,
        "intelligence_passed": bool(intelligence.get("passed")),
        "hard_case_rate": _ratio(details, "Hard cases"),
        "retrieval_recall_at_4": float(recall_match.group(1)) if recall_match else None,
        "session_grounded_advice_rate": _ratio(details, "session-grounded advice"),
        "recovery_rate": _ratio(details, "assistant recovery"),
        "source_sha256": suite.get("source_sha256"),
    }


def compare(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {
        "suite_passed": candidate["suite_passed"],
        "intelligence_passed": candidate["intelligence_passed"],
    }
    for metric in ("suite_pass_count", "hard_case_rate", "retrieval_recall_at_4", "session_grounded_advice_rate", "recovery_rate"):
        previous = baseline.get(metric)
        current = candidate.get(metric)
        checks[f"no_regression_{metric}"] = (
            current is not None and (previous is None or current >= previous)
        )
    return {"checks": checks, "passed": all(checks.values())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="HEAD~1", help="Git revision holding the baseline receipts.")
    parser.add_argument("--candidate", default="HEAD", help="Git revision holding candidate receipts.")
    args = parser.parse_args()
    baseline = summarize({name: _receipt(args.baseline, path) for name, path in RECEIPTS.items()})
    candidate = summarize({name: _receipt(args.candidate, path) for name, path in RECEIPTS.items()})
    report = {
        "schema": "kenn.candidate_scorecard.v1",
        "baseline_revision": args.baseline,
        "candidate_revision": args.candidate,
        "baseline": baseline,
        "candidate": candidate,
        "decision": compare(baseline, candidate),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["decision"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
