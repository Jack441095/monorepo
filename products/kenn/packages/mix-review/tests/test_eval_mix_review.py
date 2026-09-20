from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tooling" / "scripts"))

import eval_mix_review
from eval_mix_review import evaluate_thresholds


def _base(**overrides):
    values = {
        "case_results": [{"pass": True}],
        "precision": 100.0,
        "recall": 100.0,
        "f1": 100.0,
        "fpr": 0.0,
        "mean_latency": 20.0,
        "max_latency": 40.0,
        "corrupted_recovery_rate": 100.0,
    }
    values.update(overrides)
    return values


def test_thresholds_pass_when_all_requirements_are_met() -> None:
    result = evaluate_thresholds(**_base())

    assert all(result.values())


def test_mean_latency_failure_is_explicit() -> None:
    result = evaluate_thresholds(**_base(mean_latency=164.28))

    assert result["mean_latency"] is False


def test_case_failure_blocks_qualification_even_when_aggregate_metrics_pass() -> None:
    result = evaluate_thresholds(**_base(case_results=[{"pass": False}]))

    assert result["case_accuracy"] is False


def test_full_benchmark_run_is_qualified(monkeypatch, tmp_path) -> None:
    """These tests only ever exercised evaluate_thresholds() with synthetic
    input values -- nothing actually ran the real 9-fault-family benchmark
    end to end and asserted it qualifies. That gap hid a real bug: this
    benchmark's per-case "expected_faults" lists predated
    calibrated_lufs_bs1770/true_peak_intersample being added to
    QUALIFIED_FAULT_FAMILIES (2026-09-05), so every loud/hot/clipped case's
    now-legitimate extra findings counted as false positives -- precision
    was 65.2%, well under the 98% qualification threshold, until the
    expected-fault lists were updated to match. Redirects the report write
    to a tmp path so this doesn't mutate docs/MIX_REVIEW_BENCHMARK_REPORT.md
    on every test run."""
    monkeypatch.setattr(eval_mix_review, "PROJECT_ROOT", tmp_path)
    (tmp_path / "docs").mkdir()

    result = eval_mix_review.run_benchmark()

    assert result["qualified"] is True, result["thresholds"]
    assert result["precision"] == 100.0
    assert result["recall"] == 100.0
    assert result["fpr"] == 0.0
    assert result["mean_latency_ms"] < 100.0
    assert result["cold_start_latency_ms"] < 500.0
    assert result["max_latency_ms"] >= result["cold_start_latency_ms"]
