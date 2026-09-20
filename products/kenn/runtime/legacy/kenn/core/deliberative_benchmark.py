"""Provider-neutral benchmark runner for KENN deliberative planners."""

from __future__ import annotations

from pathlib import Path
import json
import math
from typing import Any

from kenn.core.deliberative_eval import evaluate_deliberative_plan
from kenn.core.deliberative_planner import build_deliberative_sketch_prompt
from kenn.core.session_context import build_session_context


BENCHMARK_SCHEMA = "kenn.deliberative_benchmark.v1"
RESULT_SCHEMA = "kenn.deliberative_benchmark_result.v1"


def load_benchmark(path: Path | str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != BENCHMARK_SCHEMA:
        raise ValueError(f"Benchmark must use {BENCHMARK_SCHEMA}.")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Benchmark must contain cases.")
    ids = [str(case.get("id") or "") for case in cases if isinstance(case, dict)]
    if len(ids) != len(cases) or any(not case_id for case_id in ids) or len(set(ids)) != len(ids):
        raise ValueError("Benchmark case IDs must be non-empty and unique.")
    return data


def build_benchmark_context(case: dict[str, Any]) -> dict[str, Any]:
    inputs = case.get("context") if isinstance(case.get("context"), dict) else {}
    return build_session_context(
        session_id=str(inputs.get("session_id") or f"benchmark-{case.get('id', 'case')}")[:128],
        snapshot=inputs.get("snapshot") if isinstance(inputs.get("snapshot"), dict) else None,
        mix_review_receipts=inputs.get("mix_review_receipts") or [],
        audiogen_jobs=inputs.get("audiogen_jobs") or [],
        automix_receipts=inputs.get("automix_receipts") or [],
        audition_feedback=inputs.get("audition_feedback") or [],
        device_matrix=inputs.get("device_matrix") if isinstance(inputs.get("device_matrix"), dict) else None,
        producer_preferences=inputs.get("producer_preferences") or [],
        episodic_outcomes=inputs.get("episodic_outcomes") or [],
    )


def build_prompt_pack(benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for case in benchmark["cases"]:
        context = build_benchmark_context(case)
        rows.append({
            "schema": "kenn.deliberative_prompt_case.v1",
            "case_id": case["id"],
            "category": case.get("category", "uncategorized"),
            "prompt": build_deliberative_sketch_prompt(str(case.get("goal") or ""), context),
        })
    return rows


def evaluate_prediction_set(
    benchmark: dict[str, Any],
    predictions: dict[str, Any],
) -> dict[str, Any]:
    case_results = []
    for case in benchmark["cases"]:
        case_id = case["id"]
        context = build_benchmark_context(case)
        raw_prediction = predictions.get(case_id)
        envelope = (
            raw_prediction
            if isinstance(raw_prediction, dict) and "plan" in raw_prediction
            else {}
        )
        candidate = envelope.get("plan") if envelope else raw_prediction
        latency = envelope.get("latency_ms")
        latency_ms = (
            round(float(latency), 3)
            if isinstance(latency, (int, float)) and not isinstance(latency, bool)
            and math.isfinite(float(latency)) and float(latency) >= 0
            else None
        )
        if candidate is None:
            result = {
                "schema": "kenn.deliberative_eval_result.v1",
                "passed": False,
                "score": 0.0,
                "checks": [{"name": "prediction_present", "passed": False, "details": None}],
            }
        else:
            result = evaluate_deliberative_plan(candidate, context, case.get("expectation") or {})
        case_results.append({
            "case_id": case_id,
            "category": case.get("category", "uncategorized"),
            "safety_critical": bool(case.get("safety_critical")),
            "model_provider": str(envelope.get("model_provider") or "")[:128],
            "model_id": str(envelope.get("model_id") or "")[:128],
            "latency_ms": latency_ms,
            **result,
        })

    case_count = len(case_results)
    passed_count = sum(bool(item["passed"]) for item in case_results)
    safety = [item for item in case_results if item["safety_critical"]]
    contract_valid = sum(
        bool(next((check["passed"] for check in item["checks"] if check["name"] == "contract_valid"), False))
        for item in case_results
    )
    latencies = sorted(float(item["latency_ms"]) for item in case_results if item["latency_ms"] is not None)
    p95_index = max(0, math.ceil(len(latencies) * 0.95) - 1) if latencies else 0
    return {
        "schema": RESULT_SCHEMA,
        "benchmark_id": benchmark.get("benchmark_id", "unknown"),
        "case_count": case_count,
        "passed_count": passed_count,
        "pass_rate": round(passed_count / case_count, 4),
        "mean_score": round(sum(float(item["score"]) for item in case_results) / case_count, 4),
        "contract_valid_rate": round(contract_valid / case_count, 4),
        "safety_case_count": len(safety),
        "safety_pass_rate": round(sum(bool(item["passed"]) for item in safety) / len(safety), 4) if safety else 1.0,
        "latency": {
            "sample_count": len(latencies),
            "mean_ms": round(sum(latencies) / len(latencies), 3) if latencies else None,
            "p50_ms": latencies[(len(latencies) - 1) // 2] if latencies else None,
            "p95_ms": latencies[p95_index] if latencies else None,
        },
        "models": sorted({
            f"{item['model_provider']}:{item['model_id']}"
            for item in case_results if item["model_provider"] or item["model_id"]
        }),
        "passed": passed_count == case_count,
        "cases": case_results,
    }


__all__ = [
    "BENCHMARK_SCHEMA", "RESULT_SCHEMA", "build_benchmark_context",
    "build_prompt_pack", "evaluate_prediction_set", "load_benchmark",
]
