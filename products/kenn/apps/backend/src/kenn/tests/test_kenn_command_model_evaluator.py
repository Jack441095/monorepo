"""Checks for model-comparison metrics used by the offline command evaluator."""

from __future__ import annotations

from scripts.evaluate_kenn_command_lora import _metric_delta, _summarize_results


def _row(*, status: str, comparison: str | None, latency_ms: float, contract_ok: bool = True) -> dict:
    return {
        "status": status,
        "comparison": {"status": comparison} if comparison else None,
        "latency_ms": latency_ms,
        "deterministic_contract_ok": contract_ok,
    }


def test_summary_counts_acceptance_agreement_and_latency() -> None:
    summary = _summarize_results([
        _row(status="accepted", comparison="match", latency_ms=10),
        _row(status="accepted", comparison="mismatch", latency_ms=20),
        _row(status="rejected", comparison=None, latency_ms=30, contract_ok=False),
    ])

    assert summary["counts"] == {
        "total": 3,
        "deterministic_contract_failures": 1,
        "accepted_schema": 2,
        "rejected": 1,
        "comparison_match": 1,
        "comparison_mismatch": 1,
        "comparison_incomplete": 0,
    }
    assert summary["latency_ms"] == {"mean": 20.0, "median": 20.0, "max": 30.0}


def test_metric_delta_is_adapter_minus_base() -> None:
    adapter = _summarize_results([_row(status="accepted", comparison="match", latency_ms=15)])
    baseline = _summarize_results([_row(status="rejected", comparison=None, latency_ms=25)])

    assert _metric_delta(adapter, baseline) == {
        "accepted_schema": 1,
        "rejected": -1,
        "comparison_match": 1,
        "comparison_mismatch": 0,
        "comparison_incomplete": 0,
        "latency_mean_ms": -10.0,
    }
