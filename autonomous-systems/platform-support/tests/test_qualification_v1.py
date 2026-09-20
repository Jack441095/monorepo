"""THURSDAY_EVAL_V1 qualification runner.

Executes the frozen benchmark, asserts quality gates, exports the machine
results artifact used by the Jarvis scorecard. Thresholds are the Phase-4
MVP gate: grounding must be perfect; routing/recovery >= 0.95; brief/weekly/
continuity/approval >= 0.98 (deterministic code — near-zero tolerance).
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evals"))

from thursday_eval_v1 import BENCHMARK_VERSION, EvalRunner, export_results  # noqa: E402

ARTIFACT = Path(__file__).resolve().parent.parent / "docs" / "eval_results_v1.json"

THRESHOLDS = {
    "grounding": 1.00,
    "unknown_intent": 1.00,
    "approval": 1.00,
    "continuity": 1.00,
    "recovery": 1.00,
    "brief": 1.00,
    "weekly": 1.00,
    "routing": 1.00,
    "proactivity": 1.00,
}


@pytest.fixture(scope="module")
def summary():
    return EvalRunner().run_all()


def test_benchmark_version_frozen(summary):
    assert summary["benchmark_version"] == BENCHMARK_VERSION


def test_scenario_scale(summary):
    assert summary["total_scenarios"] >= 100, (
        "frozen benchmark should carry a meaningful scenario count")


def test_all_quality_gates(summary):
    failed_gates = []
    for family, threshold in THRESHOLDS.items():
        rate = summary["families"].get(family, {}).get("rate", 0.0)
        if rate < threshold:
            failed_gates.append(f"{family}: {rate} < {threshold}")
    assert not failed_gates, f"gates failed -> {failed_gates}; details: {summary['failures']}"


def test_hallucination_rate_zero_on_company_facts(summary):
    """Any grounding/unknown_intent failure is an unsupported-claim opportunity."""
    opps = (summary["families"]["grounding"]["total"]
            + summary["families"]["unknown_intent"]["total"])
    fails = (summary["families"]["grounding"]["failed"]
             + summary["families"]["unknown_intent"]["failed"])
    assert opps > 0
    assert fails / opps == 0.0


def test_export_machine_artifact(summary):
    export_results(summary, ARTIFACT)
    data = json.loads(ARTIFACT.read_text())
    assert data["benchmark_version"] == BENCHMARK_VERSION
    assert data["total_scenarios"] == summary["total_scenarios"]


def test_failure_recovery_rate_gate(summary):
    assert summary["failure_recovery_rate"] >= 1.0
