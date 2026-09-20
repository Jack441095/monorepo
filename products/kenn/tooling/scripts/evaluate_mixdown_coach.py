#!/usr/bin/env python3
"""Evaluate deterministic Mixdown Coach priorities and abstention behavior."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))

from kenn.core.mixdown_coach import build_mixdown_coach  # noqa: E402


SCHEMA = "kenn.mixdown_coach_evaluation.v1"
CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "low_mid_with_level_delta", "category": "low_mid",
        "review": {"reference_comparison": {"lufs_delta_db": 2.0, "largest_ltas_difference": {"center_hz": 300.0, "delta_db": 5.0}}},
        "expect": {"status": "ready", "first_kind": "level_match", "contains": "low-mid masking"},
    },
    {
        "id": "sub_balance", "category": "low_end",
        "review": {"reference_comparison": {"largest_ltas_difference": {"center_hz": 60.0, "delta_db": -3.0}}},
        "expect": {"status": "ready", "contains": "kick/bass relationship"},
    },
    {
        "id": "high_end_balance", "category": "high_end",
        "review": {"reference_comparison": {"largest_ltas_difference": {"center_hz": 9000.0, "delta_db": 2.5}}},
        "expect": {"status": "ready", "contains": "hats, cymbals"},
    },
    {
        "id": "weak_difference_abstains", "category": "abstention",
        "review": {"reference_comparison": {"largest_ltas_difference": {"center_hz": 300.0, "delta_db": 0.5}}},
        "expect": {"status": "abstain"},
    },
    {
        "id": "missing_reference_abstains", "category": "abstention",
        "review": {}, "expect": {"status": "abstain"},
    },
)


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    coach = build_mixdown_coach(case["review"])
    expect = case["expect"]
    checks = coach.get("listening_checks") or []
    actions = " ".join(str(check.get("action") or "") for check in checks if isinstance(check, dict)).lower()
    passed = coach.get("status") == expect["status"]
    if expect.get("first_kind"):
        passed = passed and bool(checks) and checks[0].get("kind") == expect["first_kind"]
    if expect.get("contains"):
        passed = passed and str(expect["contains"]).lower() in actions
    passed = passed and len(checks) <= 5 and coach.get("live_target_inference_allowed") is False
    return {
        "id": case["id"], "category": case["category"], "passed": passed,
        "status": coach.get("status"), "listening_check_count": len(checks),
    }


def main() -> int:
    rows = [evaluate_case(case) for case in CASES]
    report = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(rows),
        "passed_case_count": sum(bool(row["passed"]) for row in rows),
        "all_cases_passed": all(bool(row["passed"]) for row in rows),
        "rows": rows,
        "limitations": [
            "This is a deterministic contract check, not blinded producer usefulness evidence.",
            "It verifies no Live target inference and no more than five listening checks; it does not certify generated prose or mix quality.",
        ],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_cases_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
