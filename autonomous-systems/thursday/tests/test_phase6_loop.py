"""Tests for the Phase 6 loop pieces: finance chase list + marketing backlog.

Both are derived read-only views (ledger / plans+standing suggestions).
Empty states are legitimate ("nothing to chase"), never errors.
"""

from __future__ import annotations

import thursday.ops.finance_ops as fo
import thursday.ops.marketing_ops as mo
import thursday.ops.task_ledger as tl


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(tl, "TASK_LEDGER_FILE", tmp_path / "task_ledger.json")
    monkeypatch.setattr(mo, "MARKETING_PLANS_FILE", tmp_path / "marketing_plans.json")


def test_chase_list_empty_when_nothing_open(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert fo.chase_list() == []
    assert "Nothing to chase" in fo.render_chase_list()


def test_chase_list_finds_open_payment_tasks(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    tl.create_task("finance_admin", "SIM Quote mixing £180, await payment",
                   next_action="chase politely day 3")
    tl.create_task("finance_admin", "SIM mixing delivery in progress",
                   next_action="mix the stems")
    done = tl.create_task("finance_admin", "SIM old quote paid",
                          next_action="await payment")
    tl.complete_task(done.task_id)
    items = fo.chase_list()
    assert len(items) == 1
    assert "await payment" in items[0]["objective"]
    assert "polite reminder" in fo.render_chase_list().lower() or "draft_ops" in fo.render_chase_list()


def test_chase_list_ignores_non_payment_tasks(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    tl.create_task("engineering", "Fix export crash payment-adjacent wording aside")
    # workstream filter: engineering never chased even with money words nearby
    assert fo.chase_list() == []


def test_backlog_ranks_suggestions_by_impact_over_effort():
    items = mo.backlog()
    suggestions = [i for i in items if i["kind"] == "SUGGESTION"]
    assert len(suggestions) == 6
    scores = [i["score"] for i in suggestions]
    assert scores == sorted(scores, reverse=True)
    assert suggestions[0]["score"] == 3.0  # High/Low first
    out = mo.render_backlog()
    assert "SUGGESTION" in out
    assert "waitlist-submit" in out
    assert "Why: " in out


def test_backlog_lists_real_plans_first(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    mo.create_marketing_plan("Launch content")
    items = mo.backlog()
    assert items[0]["kind"] == "DATA"
    assert "Launch content" in items[0]["item"]
