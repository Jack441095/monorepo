"""Tests for thursday/weekly_report.py (Thursday Ops upgrade, phase 4 --
REPORTING SYSTEM). Every figure in the composed report must be a real
pass-through of the underlying modules' own functions -- these tests
seed real state in each underlying store and confirm the report reflects
it exactly, not a recomputed or approximated version.
"""

from __future__ import annotations

import thursday.ops.task_ledger as tl
import thursday.ops.macro_analytics as ma
import thursday.feedback as feedback
import thursday.ops.marketing_ops as mo
import thursday.ops.advertising_ops as ao
import thursday.ops.funding_ops as fo
import thursday.ops.weekly_report as wr
import pytest


@pytest.fixture(autouse=True)
def _isolated_stores(monkeypatch, tmp_path):
    monkeypatch.setattr(tl, "TASK_LEDGER_FILE", tmp_path / "task_ledger.json")
    monkeypatch.setattr(mo, "MARKETING_PLANS_FILE", tmp_path / "marketing_plans.json")
    monkeypatch.setattr(ao, "CAMPAIGN_PLANS_FILE", tmp_path / "ad_campaign_plans.json")
    monkeypatch.setattr(feedback, "FEEDBACK_LOG", tmp_path / "feedback.jsonl")
    monkeypatch.setattr(feedback, "HABITS_FILE", tmp_path / "habits.json")
    monkeypatch.setattr(feedback, "PATTERNS_FILE", tmp_path / "patterns.json")
    monkeypatch.setattr(feedback, "SUGGESTIONS_FILE", tmp_path / "suggestions.json")
    monkeypatch.setattr("thursday.runtime_paths.runtime_dir", lambda *_a, **_kw: tmp_path)
    monkeypatch.setattr(fo, "_resolve_list_records", lambda: None)  # honest "unavailable" outside app process


def test_empty_state_is_honest_everywhere():
    report = wr.compose_weekly_report()
    assert report["tasks"]["active_count"] == 0
    assert report["macro_stats"]["total_executions"] == 0
    assert report["agent_reliability"]["total_records"] == 0
    assert report["marketing"]["plans_on_file"] == 0
    assert report["advertising"]["plans_on_file"] == 0
    rendered = wr.render_weekly_report(report)
    assert "No active tasks." in rendered
    assert "No macro executions recorded this period." in rendered
    assert "No feedback data collected yet." in rendered


def test_report_reflects_real_active_and_blocked_tasks():
    a = tl.create_task("engineering", "Fix crash on export.", priority="urgent")
    tl.update_task(a.task_id, status="active")
    b = tl.create_task("infrastructure", "Deploy readiness.")
    tl.block_task(b.task_id, "DNS not verified.")

    report = wr.compose_weekly_report()
    # "blocked" is not in task_ledger.OPEN_STATUSES, so active_tasks()
    # (and this count) deliberately excludes it -- only the urgent task.
    assert report["tasks"]["active_count"] == 1
    assert report["tasks"]["blocked_count"] == 1
    assert any("DNS not verified." in r for r in report["risks"])

    rendered = wr.render_weekly_report(report)
    assert a.task_id in rendered
    assert b.task_id in rendered
    assert "DNS not verified." in rendered


def test_report_reflects_real_macro_stats():
    ma.record_macro_execution("morning_briefing", ["ok"], 100.0)
    report = wr.compose_weekly_report()
    assert report["macro_stats"]["total_executions"] == 1
    rendered = wr.render_weekly_report(report)
    assert "Macro executions recorded: 1" in rendered


def test_report_reflects_real_marketing_and_advertising_plans():
    mo.create_marketing_plan("Prepare launch content")
    ao.create_campaign_plan("Submit")
    report = wr.compose_weekly_report()
    assert report["marketing"]["plans_on_file"] == 1
    assert report["advertising"]["plans_on_file"] == 1


def test_report_flags_zero_traction_as_a_risk(monkeypatch):
    # Real, verified zeros (not "unavailable") -- only then is the
    # pre-revenue risk allowed to fire; see the next test for the honest
    # opposite case.
    monkeypatch.setattr(fo, "_resolve_list_records", lambda: lambda table: [])
    report = wr.compose_weekly_report()
    assert any("pre-revenue" in r for r in report["risks"])


def test_report_does_not_claim_pre_revenue_when_traction_is_unverifiable():
    # Fixture's default: _resolve_list_records() -> None, i.e. app.db is
    # unreachable. Must not report "unavailable" values as if they were
    # verified zeros.
    report = wr.compose_weekly_report()
    assert not any("pre-revenue" in r for r in report["risks"])


def test_next_action_prioritizes_approval_over_blocked_over_active():
    blocked_task = tl.create_task("qa", "Regression suite.")
    tl.block_task(blocked_task.task_id, "CI runner down.")
    approval_task = tl.create_task("funding", "Submit grant.", approval_required=True)
    tl.update_task(approval_task.task_id, status="active")

    report = wr.compose_weekly_report()
    assert approval_task.task_id in report["next_action"]


def test_next_action_honest_when_nothing_open():
    report = wr.compose_weekly_report()
    assert "No open tasks" in report["next_action"]


def test_write_receipt_creates_a_real_json_file(tmp_path):
    report = wr.compose_weekly_report()
    path = wr.write_receipt(report)
    assert path != "(receipt write failed — see logs)"
    import json
    from pathlib import Path
    saved = json.loads(Path(path).read_text())
    assert saved["generated_at"] == report["generated_at"]


def test_weekly_company_report_end_to_end_includes_receipt_path():
    out = wr.weekly_company_report()
    assert "WEEKLY COMPANY REPORT" in out
    assert "Receipt saved:" in out
