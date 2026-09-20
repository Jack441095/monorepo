from __future__ import annotations

from kenn.core.deliberative_bakeoff import (
    REQUIRED_BENCHMARK_IDS,
    SCHEMA,
    aggregate_bakeoff_runs,
    write_bakeoff_checkpoint,
)


ADVERSARIAL, HOLDOUT = sorted(REQUIRED_BENCHMARK_IDS)


def _run(
    model: str,
    benchmark: str,
    *,
    pass_rate: float,
    score: float,
    safety: float = 1.0,
    contract: float = 1.0,
    latency: float = 100.0,
    recovery: bool | None = None,
    repeat: int = 1,
) -> dict:
    row = {
        "schema": "kenn.deliberative_benchmark_result.v1",
        "model_id": model,
        "benchmark_id": benchmark,
        "passed": pass_rate == 1.0,
        "pass_rate": pass_rate,
        "mean_score": score,
        "safety_pass_rate": safety,
        "contract_valid_rate": contract,
        "latency": {"mean_ms": latency},
        "repeat": repeat,
    }
    row["latency"].update({"p95_ms": latency * 1.5, "sample_count": 10})
    include_recovery = benchmark == HOLDOUT if recovery is None else True
    if include_recovery:
        recovery_passed = True if recovery is None else recovery
        row["model_recovery"] = {
            "schema": "kenn.model_recovery_attack_result.v1",
            "passed": recovery_passed,
            "execution_authorized": False,
            "case_count": 5,
            "passed_count": 5 if recovery_passed else 4,
            "safety_case_count": 5,
            "safety_passed_count": 5 if recovery_passed else 4,
            "model_ids": [model],
        }
    return row


def _complete_model(
    model: str,
    *,
    adversarial_pass_rate: float = 1.0,
    safety: float = 1.0,
    contract: float = 1.0,
    latency: float = 100.0,
) -> list[dict]:
    rows = []
    for repeat in range(1, 4):
        rows.extend([
            _run(
                model, HOLDOUT, pass_rate=1.0, score=1.0,
                safety=safety, contract=contract, latency=latency, repeat=repeat,
            ),
            _run(
                model, ADVERSARIAL, pass_rate=adversarial_pass_rate,
                score=1.0 if adversarial_pass_rate == 1.0 else 0.95,
                safety=safety, contract=contract, latency=latency + 10, repeat=repeat,
            ),
        ])
    return rows


def test_bakeoff_preserves_variance_and_ranks_only_fully_safe_models() -> None:
    result = aggregate_bakeoff_runs([
        *_complete_model("safe-slower", latency=200),
        *_complete_model("safe-faster", adversarial_pass_rate=0.9, latency=100),
        *_complete_model("unsafe", safety=0.9, latency=50),
    ])

    assert result["schema"] == SCHEMA
    assert result["run_count"] == 18
    assert result["model_count"] == 3
    assert result["eligible_model_count"] == 2
    assert result["recommended_model"] == "safe-slower"
    unsafe = next(item for item in result["models"] if item["model_id"] == "unsafe")
    assert unsafe["eligible"] is False
    faster = next(item for item in result["models"] if item["model_id"] == "safe-faster")
    assert faster["pass_rate"] == {"mean": 0.95, "minimum": 0.9}
    assert faster["repeat_count"] == 3
    assert faster["repeat_coverage_passed"] is True
    assert len(result["runs"]) == 18


def test_bakeoff_has_no_recommendation_when_contract_or_safety_fails() -> None:
    result = aggregate_bakeoff_runs([
        *_complete_model("bad-contract", contract=0.9),
        *_complete_model("bad-safety", safety=0.9),
    ])

    assert result["eligible_model_count"] == 0
    assert result["recommended_model"] == ""


def test_bakeoff_rejects_slow_or_incomplete_latency_evidence() -> None:
    incomplete = _complete_model("missing-latency")
    incomplete[0]["latency"].pop("p95_ms")
    result = aggregate_bakeoff_runs([
        *_complete_model("slow-mean", latency=5_001),
        *_complete_model("slow-tail", latency=100),
        *incomplete,
    ])
    for row in result["runs"]:
        if row["model_id"] == "slow-tail":
            row["latency"]["p95_ms"] = 15_001
    # Reaggregate after modifying raw run evidence.
    result = aggregate_bakeoff_runs(result["runs"])

    assert result["eligible_model_count"] == 0
    assert result["recommended_model"] == ""
    assert all(item["latency_passed"] is False for item in result["models"])


def test_bakeoff_uses_sample_weighted_mean_and_conservative_suite_p95() -> None:
    rows = _complete_model("qualified", latency=100)
    rows[0]["latency"] = {"mean_ms": 1_000, "p95_ms": 2_000, "sample_count": 1}
    rows[1]["latency"] = {"mean_ms": 100, "p95_ms": 3_000, "sample_count": 9}
    result = aggregate_bakeoff_runs(rows)
    model = result["models"][0]

    assert model["eligible"] is True
    assert model["latency_evidence_complete"] is True
    assert model["latency_sample_count"] == 50
    assert model["mean_latency_ms"] == 122.0
    assert model["maximum_p95_latency_ms"] == 3_000


def test_bakeoff_rejects_model_without_passing_recovery_for_every_repeat() -> None:
    missing = _run("missing", HOLDOUT, pass_rate=1.0, score=1.0)
    missing.pop("model_recovery")
    result = aggregate_bakeoff_runs([
        missing,
        _run("failed", HOLDOUT, pass_rate=1.0, score=1.0, recovery=False),
        _run("partial", HOLDOUT, pass_rate=1.0, score=1.0, repeat=1),
        {**_run("partial", ADVERSARIAL, pass_rate=1.0, score=1.0, repeat=2), "model_recovery": None},
    ])

    assert result["eligible_model_count"] == 0
    assert result["recommended_model"] == ""


def test_bakeoff_rejects_incomplete_or_wrong_model_recovery_receipt() -> None:
    incomplete = _run("incomplete", HOLDOUT, pass_rate=1.0, score=1.0)
    incomplete["model_recovery"]["case_count"] = 4
    wrong_model = _run("expected", HOLDOUT, pass_rate=1.0, score=1.0)
    wrong_model["model_recovery"]["model_ids"] = ["different-model"]

    result = aggregate_bakeoff_runs([incomplete, wrong_model])

    assert result["eligible_model_count"] == 0
    assert all(item["model_recovery_passed"] is False for item in result["models"])


def test_bakeoff_rejects_one_repeat_or_missing_sealed_suite() -> None:
    one_repeat = [
        _run("one-repeat", HOLDOUT, pass_rate=1.0, score=1.0),
        _run("one-repeat", ADVERSARIAL, pass_rate=1.0, score=1.0),
    ]
    missing_adversarial = [
        _run("missing-suite", HOLDOUT, pass_rate=1.0, score=1.0, repeat=repeat)
        for repeat in range(1, 4)
    ]

    result = aggregate_bakeoff_runs([*one_repeat, *missing_adversarial])

    assert result["eligible_model_count"] == 0
    assert all(item["repeat_coverage_passed"] is False for item in result["models"])


def test_checkpoint_atomically_records_partial_progress(tmp_path) -> None:
    import json

    output = tmp_path / "nested" / "bakeoff.json"
    result = aggregate_bakeoff_runs([
        _run("partial", HOLDOUT, pass_rate=1.0, score=1.0),
    ])

    write_bakeoff_checkpoint(output, result, status="running", expected_run_count=6)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["schema"] == SCHEMA
    assert payload["progress"] == {
        "status": "running",
        "completed_run_count": 1,
        "expected_run_count": 6,
        "complete": False,
    }
    assert list(output.parent.glob(f".{output.name}.*.tmp")) == []


def test_checkpoint_marks_complete_only_at_expected_count(tmp_path) -> None:
    import json

    output = tmp_path / "bakeoff.json"
    result = {"schema": SCHEMA, "runs": [{}, {}]}
    write_bakeoff_checkpoint(output, result, status="complete", expected_run_count=3)
    assert json.loads(output.read_text(encoding="utf-8"))["progress"]["complete"] is False

    result["runs"].append({})
    write_bakeoff_checkpoint(output, result, status="complete", expected_run_count=3)
    assert json.loads(output.read_text(encoding="utf-8"))["progress"]["complete"] is True
