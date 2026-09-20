"""Phase-0 P0-D regression: scheduler exactly-once occurrence claims.

docs/audits/2026-08-20-thursday-nitedsp-forensic-audit.md and the companion
platform master report found that `thursday/scheduler.py`'s `should_run()` /
`run_scheduled_tasks()` evaluated a 5-minute time window with no lock,
lease, or unique constraint -- two overlapping poll cycles (e.g. two
scheduler processes, or the same process re-entered before the first run
finished) could dispatch the same scheduled task twice, causing a real
duplicate external side effect (a duplicate invoice follow-up email, a
duplicate outreach send, etc).

These tests exercise the new `claim_occurrence()`/`complete_occurrence()`
SQLite-backed atomic claim and `run_scheduled_tasks()`'s use of it, including
a genuine concurrent-claim race with a thread pool (not just a serial
"call twice" simulation).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from thursday import scheduler


@pytest.fixture
def isolated_claims_db(tmp_path, monkeypatch):
    monkeypatch.setenv("THURSDAY_SCHEDULER_CLAIMS_DB", str(tmp_path / "claims.sqlite3"))
    return tmp_path


def test_claim_occurrence_wins_exactly_once(isolated_claims_db):
    assert scheduler.claim_occurrence("invoice_followups", "2026-08-20") is True
    assert scheduler.claim_occurrence("invoice_followups", "2026-08-20") is False


def test_different_occurrence_is_independently_claimable(isolated_claims_db):
    assert scheduler.claim_occurrence("invoice_followups", "2026-08-20") is True
    assert scheduler.claim_occurrence("invoice_followups", "2026-08-21") is True
    assert scheduler.claim_occurrence("archive_cold_leads", "2026-08-20") is True


def test_concurrent_claims_on_the_same_occurrence_produce_exactly_one_winner(isolated_claims_db):
    """A genuine race: many threads hammer claim_occurrence for the identical
    (task, occurrence) pair at once. Exactly one must win."""
    results = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [
            pool.submit(scheduler.claim_occurrence, "lead_nurturing", "2026-W34")
            for _ in range(16)
        ]
        results = [f.result() for f in futures]

    assert results.count(True) == 1, f"expected exactly one winner, got {results.count(True)}"
    assert results.count(False) == 15


def test_occurrence_key_distinguishes_daily_weekly_monthly():
    daily = {"name": "invoice_followups", "time": "09:00"}
    weekly = {"name": "lead_nurturing", "day": "monday", "time": "10:00"}
    monthly = {"name": "revenue_forecast", "day": 1, "time": "08:00"}
    now_dt = datetime(2026, 8, 20, 9, 2, tzinfo=ZoneInfo("Europe/London"))

    assert scheduler._occurrence_key(daily, now_dt) == "invoice_followups:2026-08-20"
    assert scheduler._occurrence_key(weekly, now_dt) == "lead_nurturing:2026-W34"
    assert scheduler._occurrence_key(monthly, now_dt) == "revenue_forecast:2026-08"

    # A different day -> a different daily occurrence.
    next_day = datetime(2026, 8, 21, 9, 2, tzinfo=ZoneInfo("Europe/London"))
    assert scheduler._occurrence_key(daily, next_day) != scheduler._occurrence_key(daily, now_dt)


def test_run_scheduled_tasks_does_not_double_dispatch_the_same_occurrence(isolated_claims_db):
    """End-to-end: two back-to-back calls to run_scheduled_tasks() within the
    same should_run() window and the same calendar occurrence must dispatch
    the underlying agent method exactly once, not twice."""
    call_count = {"n": 0}

    def fake_dispatch(agent_name, method_name, params=None):
        call_count["n"] += 1
        return {"ok": True, "agent": agent_name, "method": method_name}

    with (
        patch.object(scheduler, "should_run", return_value=True),
        patch.object(scheduler, "dispatch_agent", side_effect=fake_dispatch),
        patch.object(
            scheduler,
            "load_schedules",
            return_value={
                "daily": [{"name": "invoice_followups", "time": "09:00", "agent": "FollowupAgent", "method": "check_invoice_followups"}],
                "weekly": [],
                "monthly": [],
            },
        ),
    ):
        first = scheduler.run_scheduled_tasks()
        second = scheduler.run_scheduled_tasks()

    assert call_count["n"] == 1, "the same scheduled occurrence was dispatched more than once"
    assert first["results"][0]["run_result"]["ok"] is True
    assert second["results"][0]["run_result"].get("skipped") == "already_claimed"


def test_run_scheduled_tasks_concurrent_pollers_dispatch_exactly_once(isolated_claims_db):
    """The realistic failure mode the audit described: two scheduler
    processes (simulated here as two threads) both observe should_run()==True
    for the same occurrence and race to dispatch it."""
    call_count = {"n": 0}

    def fake_dispatch(agent_name, method_name, params=None):
        call_count["n"] += 1
        return {"ok": True, "agent": agent_name, "method": method_name}

    with (
        patch.object(scheduler, "should_run", return_value=True),
        patch.object(scheduler, "dispatch_agent", side_effect=fake_dispatch),
        patch.object(
            scheduler,
            "load_schedules",
            return_value={
                "daily": [{"name": "invoice_followups", "time": "09:00", "agent": "FollowupAgent", "method": "check_invoice_followups"}],
                "weekly": [],
                "monthly": [],
            },
        ),
    ):
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(scheduler.run_scheduled_tasks) for _ in range(8)]
            [f.result() for f in futures]

    assert call_count["n"] == 1, f"expected exactly one dispatch across concurrent pollers, got {call_count['n']}"


def test_failed_occurrence_is_recorded_and_not_retried_within_the_same_window(isolated_claims_db):
    """Deterministic failure behaviour: a claimed occurrence whose dispatch
    fails is recorded as 'failed', not left claimable again within the same
    occurrence window (retry policy for scheduled tasks is out of scope for
    this Phase-0 pass; the next distinct occurrence, e.g. the next day, is a
    fresh claim)."""
    def failing_dispatch(agent_name, method_name, params=None):
        return {"ok": False, "agent": agent_name, "method": method_name, "error": "boom"}

    with (
        patch.object(scheduler, "should_run", return_value=True),
        patch.object(scheduler, "dispatch_agent", side_effect=failing_dispatch),
        patch.object(
            scheduler,
            "load_schedules",
            return_value={
                "daily": [{"name": "invoice_followups", "time": "09:00", "agent": "FollowupAgent", "method": "check_invoice_followups"}],
                "weekly": [],
                "monthly": [],
            },
        ),
    ):
        first = scheduler.run_scheduled_tasks()
        second = scheduler.run_scheduled_tasks()

    assert first["results"][0]["run_result"]["ok"] is False
    # Second poll in the same window/occurrence must not re-dispatch either.
    assert second["results"][0]["run_result"].get("skipped") == "already_claimed"


def test_claim_persists_across_a_fresh_connection(isolated_claims_db):
    """Simulates a process restart: a claim made by one connection must be
    visible (and still block a re-claim) from a brand-new connection to the
    same on-disk database."""
    assert scheduler.claim_occurrence("invoice_followups", "2026-08-20") is True

    import sqlite3

    conn = sqlite3.connect(str(scheduler._claims_db_path()))
    try:
        row = conn.execute(
            "SELECT status FROM scheduled_task_claims WHERE task_name = ? AND occurrence_key = ?",
            ("invoice_followups", "2026-08-20"),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "processing"

    # A fresh claim_occurrence() call (its own new connection) must still see it.
    assert scheduler.claim_occurrence("invoice_followups", "2026-08-20") is False
