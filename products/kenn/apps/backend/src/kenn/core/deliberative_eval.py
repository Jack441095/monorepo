"""Trajectory-level scoring for model-generated deliberative plans."""

from __future__ import annotations

from typing import Any

from kenn.core.deliberative_plan import validate_deliberative_plan


def _is_subsequence(expected: list[Any], actual: list[Any]) -> bool:
    if not expected:
        return True
    position = 0
    for item in actual:
        if item == expected[position]:
            position += 1
            if position == len(expected):
                return True
    return False


def evaluate_deliberative_plan(
    candidate: Any,
    context: dict[str, Any],
    expectation: dict[str, Any],
) -> dict[str, Any]:
    """Score plan shape and ordering without treating prose similarity as skill."""
    validation = validate_deliberative_plan(candidate, context)
    checks: list[dict[str, Any]] = [{
        "name": "contract_valid",
        "passed": bool(validation.get("ok")),
        "details": validation.get("errors", []),
    }]
    if not validation.get("ok") or not isinstance(candidate, dict):
        return {
            "schema": "kenn.deliberative_eval_result.v1",
            "passed": False,
            "checks": checks,
            "score": 0.0,
        }

    steps = candidate.get("steps", [])
    kinds = [step.get("kind") for step in steps]
    actions = [step.get("action") for step in steps]
    positions = {step.get("step_id"): index for index, step in enumerate(steps)}

    def add(name: str, passed: bool, details: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "details": details})

    if "status" in expectation:
        add("expected_status", candidate.get("status") == expectation["status"], {
            "expected": expectation["status"], "actual": candidate.get("status"),
        })
    for kind in expectation.get("required_kinds", []):
        add(f"required_kind:{kind}", kind in kinds)
    for action in expectation.get("required_actions", []):
        add(f"required_action:{action}", action in actions)
    for kind in expectation.get("forbidden_kinds", []):
        add(f"forbidden_kind:{kind}", kind not in kinds)
    if "ordered_kinds" in expectation:
        expected_kinds = list(expectation["ordered_kinds"])
        add("ordered_kinds", _is_subsequence(expected_kinds, kinds), {
            "expected": expected_kinds, "actual": kinds,
        })
    if "ordered_actions" in expectation:
        expected_actions = list(expectation["ordered_actions"])
        add("ordered_actions", _is_subsequence(expected_actions, actions), {
            "expected": expected_actions, "actual": actions,
        })
    if "max_steps" in expectation:
        add("max_steps", len(steps) <= int(expectation["max_steps"]), {
            "maximum": int(expectation["max_steps"]), "actual": len(steps),
        })
    for before, after in expectation.get("ordered_steps", []):
        passed = before in positions and after in positions and positions[before] < positions[after]
        add(f"ordered:{before}->{after}", passed)

    passed_count = sum(bool(check["passed"]) for check in checks)
    return {
        "schema": "kenn.deliberative_eval_result.v1",
        "passed": all(bool(check["passed"]) for check in checks),
        "checks": checks,
        "score": round(passed_count / len(checks), 4),
    }


__all__ = ["evaluate_deliberative_plan"]
