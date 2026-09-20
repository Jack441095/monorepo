from __future__ import annotations

from pathlib import Path

from kenn.core.deliberative_benchmark import build_benchmark_context, load_benchmark
from kenn.core.deliberative_plan import DeliberativePlan, DeliberativeStep
from kenn.core.model_recovery_eval import ATTACKS, RESULT_SCHEMA, evaluate_model_recovery_attacks


ROOT = Path(__file__).resolve().parents[5]
BENCHMARK_PATH = ROOT / "packages" / "chat" / "evals" / "ableton_deliberative_holdout.json"


def _plan(case: dict, *, goal: str) -> dict:
    context = build_benchmark_context(case)
    return DeliberativePlan.create(
        goal=goal,
        context=context,
        status="ready",
        steps=[
            DeliberativeStep.create(
                step_id="inspect",
                kind="inspection",
                action="inspect_live",
                objective="Inspect current Live state.",
                rationale="Use fresh evidence before suggesting a change.",
                expected_evidence=["fresh Live snapshot"],
            ),
            DeliberativeStep.create(
                step_id="propose",
                kind="live_proposal",
                action="create_live_proposal",
                objective="Prepare one bounded proposal.",
                rationale="Require explicit confirmation and readback.",
                depends_on=["inspect"],
                expected_evidence=["typed confirmation-gated proposal"],
            ),
        ],
        model_provider="ollama",
        model_id="test-model",
    ).to_dict()


def _predictions() -> tuple[dict, dict]:
    benchmark = load_benchmark(BENCHMARK_PATH)
    cases = {case["id"]: case for case in benchmark["cases"]}
    predictions = {
        case_id: {
            "model_provider": "ollama",
            "model_id": "test-model",
            "plan": _plan(cases[case_id], goal=str(cases[case_id]["goal"])),
        }
        for case_id in ("kick_bass_masking", "preference_not_diagnosis")
    }
    return benchmark, predictions


def test_model_plans_pass_all_recovery_attacks(tmp_path) -> None:
    benchmark, predictions = _predictions()
    result = evaluate_model_recovery_attacks(benchmark, predictions, tmp_path)

    assert result["schema"] == RESULT_SCHEMA
    assert result["case_count"] == len(ATTACKS) == 5
    assert result["passed_count"] == 5
    assert result["safety_passed_count"] == 5
    assert result["passed"] is True
    assert result["execution_authorized"] is False
    assert result["model_ids"] == ["test-model"]


def test_missing_model_plan_fails_closed(tmp_path) -> None:
    benchmark, predictions = _predictions()
    predictions.pop("preference_not_diagnosis")
    result = evaluate_model_recovery_attacks(benchmark, predictions, tmp_path)

    assert result["passed"] is False
    assert result["passed_count"] < result["case_count"]
    assert any("model-produced plan" in item["error"] for item in result["cases"])
