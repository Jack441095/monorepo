"""Tests for KENN benchmark gate checks."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

from kenn_benchmark_gate import evaluate_gate, latest_summary  # noqa: E402


def test_benchmark_gate_passes_clean_summary() -> None:
    report = evaluate_gate(
        {
            "total_runs": 4,
            "passed_runs": 4,
            "failed_runs": 0,
            "duration_ms": {"p95": 50},
            "source_diversity_warning_runs": 0,
            "case_category_counts": {"adversarial": 1, "business": 1},
            "case_category_pass_rates": {"adversarial": 1.0, "business": 1.0},
            "unique_questions": 4,
            "grounding_contract": {
                "citation_validity": 1.0,
                "required_fact_coverage": 1.0,
                "abstention_precision": 1.0,
                "critical_unsupported_claims": 0,
            },
        },
        min_pass_rate=1.0,
        max_p95_ms=100,
        max_source_warnings=0,
        require_categories=("adversarial", "business"),
        min_unique_questions=4,
        min_citation_validity=0.95,
        min_required_fact_coverage=0.9,
        min_abstention_precision=0.9,
        max_critical_unsupported_claims=0,
    )

    assert report["ok"] is True


def test_benchmark_gate_reports_failures() -> None:
    report = evaluate_gate(
        {
            "total_runs": 4,
            "passed_runs": 3,
            "failed_runs": 1,
            "duration_ms": {"p95": 150},
            "source_diversity_warning_runs": 2,
            "case_category_counts": {"adversarial": 1},
            "case_category_pass_rates": {"adversarial": 0.0},
            "unique_questions": 3,
            "grounding_contract": {
                "citation_validity": 0.5,
                "required_fact_coverage": 0.5,
                "abstention_precision": 0.5,
                "critical_unsupported_claims": 1,
            },
        },
        min_pass_rate=1.0,
        max_p95_ms=100,
        max_source_warnings=0,
        require_categories=("adversarial", "business"),
        min_unique_questions=4,
        min_citation_validity=0.95,
        min_required_fact_coverage=0.9,
        min_abstention_precision=0.9,
        max_critical_unsupported_claims=0,
    )

    assert report["ok"] is False
    assert any("pass_rate" in item for item in report["failures"])
    assert any("p95 latency" in item for item in report["failures"])
    assert any("source diversity" in item for item in report["failures"])
    assert any("business" in item for item in report["failures"])
    assert any("citation validity" in item for item in report["failures"])
    assert any("required-fact coverage" in item for item in report["failures"])
    assert any("abstention precision" in item for item in report["failures"])
    assert any("critical unsupported" in item for item in report["failures"])


def test_latest_summary_skips_newer_partial_suite(tmp_path: Path) -> None:
    import json

    complete = {
        "total_runs": 4,
        "case_category_counts": {
            "adversarial": 1,
            "ambiguity": 1,
            "business": 1,
            "refusal": 1,
        },
    }
    partial = {"total_runs": 1, "case_category_counts": {"standard": 1}}
    old = tmp_path / "ableton_benchmark_20260701T000000Z.json"
    new = tmp_path / "ableton_benchmark_20260701T000100Z.json"
    old.write_text(json.dumps(complete), encoding="utf-8")
    new.write_text(json.dumps(partial), encoding="utf-8")

    selected = latest_summary(tmp_path, ("adversarial", "ambiguity", "business", "refusal"))

    assert selected is not None
    assert selected["path"] == str(old)
