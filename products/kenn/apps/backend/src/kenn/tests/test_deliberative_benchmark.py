from __future__ import annotations

from pathlib import Path

from kenn.core.deliberative_benchmark import (
    build_benchmark_context,
    build_prompt_pack,
    evaluate_prediction_set,
    load_benchmark,
)
from kenn.core.deliberative_plan import DeliberativePlan, DeliberativeStep


ROOT = Path(__file__).resolve().parents[5]
BENCHMARK = ROOT / "packages" / "chat" / "evals" / "ableton_deliberative_holdout.json"


def _valid_prediction(case: dict) -> dict:
    context = build_benchmark_context(case)
    expectation = case["expectation"]
    status = expectation["status"]
    if status == "refused":
        kinds_actions = [("refusal", "refuse")]
    elif status == "needs_clarification":
        kinds_actions = [("clarification", "ask_user")]
    else:
        action_kind = {
            "inspect_live": "inspection", "review_generated_asset": "inspection",
            "compare_offline_candidate": "inspection", "create_live_proposal": "live_proposal",
        }
        kind_action = {"inspection": "inspect_live", "live_proposal": "create_live_proposal"}
        ordered = expectation.get("ordered_actions") or expectation.get("required_actions")
        if ordered:
            kinds_actions = [(action_kind[action], action) for action in ordered]
        else:
            kinds_actions = [(kind, kind_action[kind]) for kind in expectation.get("ordered_kinds", ["inspection"])]
    steps = []
    for index, (kind, action) in enumerate(kinds_actions, start=1):
        steps.append(DeliberativeStep.create(
            step_id=f"step-{index}", kind=kind, action=action,
            objective=f"Handle {action} safely.", rationale="Follow the observed context and benchmark goal.",
            depends_on=[f"step-{index - 1}"] if index > 1 else [], expected_evidence=["typed evidence"],
        ))
    return DeliberativePlan.create(
        goal=case["goal"], context=context, status=status, steps=steps,
        model_provider="fixture", model_id="gold-shape",
    ).to_dict()


def test_holdout_is_well_formed_and_prompt_pack_hides_expectations() -> None:
    benchmark = load_benchmark(BENCHMARK)
    prompts = build_prompt_pack(benchmark)

    assert len(prompts) == 10
    assert len({row["case_id"] for row in prompts}) == 10
    assert all("expectation" not in row["prompt"] for row in prompts)
    assert all("kenn.deliberative_plan_sketch.v1" in row["prompt"] for row in prompts)
    assert all("snapshot_fingerprint" not in row["prompt"] for row in prompts)


def test_gold_shape_predictions_pass_all_holdout_trajectory_checks() -> None:
    benchmark = load_benchmark(BENCHMARK)
    predictions = {case["id"]: _valid_prediction(case) for case in benchmark["cases"]}

    result = evaluate_prediction_set(benchmark, predictions)

    assert result["passed"] is True
    assert result["pass_rate"] == 1.0
    assert result["contract_valid_rate"] == 1.0
    assert result["safety_pass_rate"] == 1.0


def test_missing_and_unsafe_predictions_fail_aggregate() -> None:
    benchmark = load_benchmark(BENCHMARK)
    first = benchmark["cases"][0]
    unsafe = _valid_prediction(first)
    unsafe["execution_authorized"] = True

    result = evaluate_prediction_set(benchmark, {first["id"]: unsafe})

    assert result["passed"] is False
    assert result["passed_count"] == 0
    assert result["contract_valid_rate"] == 0.0


def test_prediction_envelopes_report_model_and_latency_without_affecting_plan() -> None:
    benchmark = load_benchmark(BENCHMARK)
    predictions = {
        case["id"]: {
            "plan": _valid_prediction(case),
            "model_provider": "local",
            "model_id": "candidate-a",
            "latency_ms": 100 + index,
        }
        for index, case in enumerate(benchmark["cases"])
    }

    result = evaluate_prediction_set(benchmark, predictions)

    assert result["passed"] is True
    assert result["models"] == ["local:candidate-a"]
    assert result["latency"] == {
        "sample_count": 10, "mean_ms": 104.5, "p50_ms": 104.0, "p95_ms": 109.0,
    }


def test_rejected_prediction_envelope_still_counts_model_latency() -> None:
    benchmark = load_benchmark(BENCHMARK)
    first = benchmark["cases"][0]
    result = evaluate_prediction_set(benchmark, {
        first["id"]: {
            "plan": None,
            "model_provider": "transformers",
            "model_id": "rejected-candidate",
            "latency_ms": 1234.5,
            "error": "invalid model sketch",
        },
    })

    first_result = result["cases"][0]
    assert first_result["passed"] is False
    assert first_result["model_provider"] == "transformers"
    assert first_result["model_id"] == "rejected-candidate"
    assert first_result["latency_ms"] == 1234.5
    assert result["models"] == ["transformers:rejected-candidate"]
    assert result["latency"]["sample_count"] == 1
    assert result["latency"]["mean_ms"] == 1234.5
