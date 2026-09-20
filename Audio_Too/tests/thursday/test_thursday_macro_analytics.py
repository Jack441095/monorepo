"""Tests for thursday/macro_analytics.py (D2.3).

Macros had no structured execution log at all -- this module is the
observation layer, called from the two execute_macro() call sites in
thursday/orchestrator.py rather than from inside thursday/macros/__init__.py
itself (deliberately left untouched -- that function is security-sensitive,
see its own module docstring). Outcome classification relies on
execute_macro()'s existing, already-shipped result-string conventions
(D1.3's partial-success format), not on any new return-value contract.
"""

from __future__ import annotations

import thursday.ops.macro_analytics as macro_analytics
from thursday.registry.handlers import _handle_macro_stats


def _seed(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "thursday.runtime_paths.runtime_dir",
        lambda *_a, **_kw: tmp_path,
    )


# ── classify_outcome ────────────────────────────────────────────────────


def test_classify_outcome_completed_for_normal_results():
    assert macro_analytics.classify_outcome(["Invoiced Jordan £200."]) == "completed"


def test_classify_outcome_completed_for_empty_results():
    assert macro_analytics.classify_outcome([]) == "completed"


def test_classify_outcome_failed_matches_d13_partial_success_format():
    # Exact wording from thursday/macros/__init__.py's err_msg construction.
    results = ["Stages step1, step2 completed. AutoMix step failed: connection refused."]
    assert macro_analytics.classify_outcome(results) == "failed"


def test_classify_outcome_paused_matches_confirmation_pause_wording():
    results = [
        "This step would run Send Invoice with risk level 'external_communication'. "
        "It has not run. To approve this exact step within five minutes, reply: confirm abc123"
    ]
    assert macro_analytics.classify_outcome(results) == "paused_for_confirmation"


# ── record_macro_execution / get_macro_stats round-trip ────────────────


def test_no_executions_reports_zero(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    stats = macro_analytics.get_macro_stats()
    assert stats == {"total_executions": 0, "macros": {}}


def test_record_and_aggregate_single_macro(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    macro_analytics.record_macro_execution("morning_briefing", ["done"], 120.0)
    macro_analytics.record_macro_execution("morning_briefing", ["done"], 80.0)
    macro_analytics.record_macro_execution(
        "morning_briefing", ["Stages a completed. b failed: timeout."], 200.0,
    )

    stats = macro_analytics.get_macro_stats()
    assert stats["total_executions"] == 3
    entry = stats["macros"]["morning_briefing"]
    assert entry["fires"] == 3
    assert entry["completed"] == 2
    assert entry["failed"] == 1
    assert entry["paused_for_confirmation"] == 0
    assert entry["success_rate"] == round(2 / 3, 3)
    # avg_elapsed_ms is over *completed* runs only (120, 80), not the failed one.
    assert entry["avg_elapsed_ms"] == 100.0


def test_multiple_macros_sorted_independently(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    macro_analytics.record_macro_execution("weekly_summary", ["ok"], 50.0)
    macro_analytics.record_macro_execution("mix_review_full_pipeline", ["ok"], 500.0)
    macro_analytics.record_macro_execution("mix_review_full_pipeline", ["ok"], 700.0)

    stats = macro_analytics.get_macro_stats()
    assert set(stats["macros"]) == {"weekly_summary", "mix_review_full_pipeline"}
    assert stats["macros"]["mix_review_full_pipeline"]["fires"] == 2
    assert stats["macros"]["weekly_summary"]["fires"] == 1


def test_logging_failure_never_raises(monkeypatch):
    # Best-effort contract, matching subagent_runtime._log_execution_trace:
    # a broken analytics path must not surface to the caller.
    def _boom(*_a, **_kw):
        raise OSError("disk full")

    monkeypatch.setattr("thursday.runtime_paths.runtime_dir", _boom)
    macro_analytics.record_macro_execution("x", ["ok"], 10.0)  # must not raise


# ── _handle_macro_stats formatting ──────────────────────────────────────


def test_handler_reports_no_data_honestly(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    out = _handle_macro_stats()
    assert "No macro executions recorded yet" in out


def test_handler_formats_fires_and_success_rate(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    macro_analytics.record_macro_execution("new_client_onboard", ["ok"], 150.0)
    macro_analytics.record_macro_execution("new_client_onboard", ["ok"], 150.0)

    out = _handle_macro_stats()
    assert "2 total executions" in out
    assert "new_client_onboard: 2 fires · 100% completed (0 failed, 0 paused) · 150ms avg" in out


def test_handler_orders_by_fire_count_descending(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    macro_analytics.record_macro_execution("rare_macro", ["ok"], 10.0)
    for _ in range(3):
        macro_analytics.record_macro_execution("frequent_macro", ["ok"], 10.0)

    out = _handle_macro_stats()
    assert out.index("frequent_macro") < out.index("rare_macro")
