from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "compare_candidate_scorecards.py"
module = importlib.util.module_from_spec(
    spec := importlib.util.spec_from_file_location("candidate_scorecards", SCRIPT)
)
assert spec.loader
spec.loader.exec_module(module)


def test_summary_extracts_qualified_metrics() -> None:
    summary = module.summarize({
        "automated_suite": {"passed": True, "summary": "925 passed, 5 skipped", "source_sha256": "abc"},
        "intelligence": {"passed": True, "details": "Hard cases 15/15; hybrid recall@4 1.0; session-grounded advice 6/6; assistant recovery 8/8"},
    })

    assert summary["suite_pass_count"] == 925
    assert summary["hard_case_rate"] == 1.0
    assert summary["retrieval_recall_at_4"] == 1.0
    assert summary["recovery_rate"] == 1.0


def test_comparison_rejects_quality_or_suite_regression() -> None:
    baseline = {"suite_passed": True, "intelligence_passed": True, "suite_pass_count": 10,
                "hard_case_rate": 1.0, "retrieval_recall_at_4": 1.0,
                "session_grounded_advice_rate": 1.0, "recovery_rate": 1.0}
    candidate = {**baseline, "suite_pass_count": 9, "retrieval_recall_at_4": 0.75}

    result = module.compare(baseline, candidate)

    assert result["passed"] is False
    assert result["checks"]["no_regression_suite_pass_count"] is False
    assert result["checks"]["no_regression_retrieval_recall_at_4"] is False
