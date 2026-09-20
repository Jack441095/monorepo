"""Tests for the Daily Brief composer (`thursday/daily_brief.py`).

Covers:
- happy-path composition across all sources
- graceful per-section degradation when a source raises
- empty-state behavior (no reminders, no receipts, no schedules)
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from thursday import action_receipts, daily_brief


TODAY = date(2026, 8, 22)


@pytest.fixture(autouse=True)
def _isolated_receipts_db(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "THURSDAY_ACTION_RECEIPTS_DB", str(tmp_path / "receipts.sqlite3")
    )


@pytest.fixture(autouse=True)
def _isolated_reminders(tmp_path, monkeypatch):
    # REMINDERS_FILE is resolved from CALENDAR_DIR at import time, so point
    # it at an empty temp file rather than relying on env vars.
    monkeypatch.setattr(
        daily_brief.scheduling,
        "REMINDERS_FILE",
        tmp_path / "reminders.json",
    )
    # Business-status TTL cache must not leak between tests or mask
    # source-failure patches.
    from thursday import status_cache

    status_cache.invalidate()
    yield
    status_cache.invalidate()


# ─── Happy path ──────────────────────────────────────────────────────────


def test_compose_happy_path_all_sections_ok():
    brief = daily_brief.compose_daily_brief(today=TODAY)

    assert brief["today"] == TODAY.isoformat()
    assert set(brief["sections"]) == set(daily_brief.BRIEF_SECTIONS)
    assert brief["summary"]["unavailable"] == []
    assert sorted(brief["summary"]["available"]) == sorted(
        daily_brief.BRIEF_SECTIONS
    )
    for section in brief["sections"].values():
        assert section["status"] == "ok"
        assert "error" not in section


def test_render_happy_path_contains_all_sections():
    brief, text = daily_brief.build_daily_brief(today=TODAY)

    assert f"# Daily Brief — {TODAY.isoformat()}" in text
    for heading in (
        "## Business Status",
        "## Company State",
        "## Today",
        "## Week Ahead",
        "## Agent Activity",
        "## Scheduled Tasks",
    ):
        assert heading in text
    assert "unavailable" not in text


def test_receipts_appear_in_brief():
    receipt_id = action_receipts.receipt_id_for_token("tok-1")
    action_receipts.claim_action(
        receipt_id, session_id="s1", service_id="email.send", text="hi"
    )
    action_receipts.complete_action(receipt_id, response_text="sent")

    brief = daily_brief.compose_daily_brief(today=TODAY)
    receipts = brief["sections"]["agent_receipts"]["payload"]
    assert len(receipts) == 1
    assert receipts[0]["service_id"] == "email.send"
    assert receipts[0]["status"] == "completed"

    _, text = daily_brief.build_daily_brief(today=TODAY)
    assert "email.send" in text


# ─── Graceful degradation ────────────────────────────────────────────────


def test_source_raise_marks_section_unavailable_only():
    with patch.object(
        daily_brief.client,
        "business_status",
        side_effect=RuntimeError("cli exploded"),
    ):
        brief = daily_brief.compose_daily_brief(today=TODAY)

    biz = brief["sections"]["business_status"]
    assert biz["status"] == "unavailable"
    assert "cli exploded" in biz["error"]
    # every other section still composed
    assert brief["summary"]["unavailable"] == ["business_status"]
    for name in ("agenda", "week_ahead", "agent_receipts", "scheduler"):
        assert brief["sections"][name]["status"] == "ok"


def test_render_marks_unavailable_section():
    with patch.object(
        daily_brief.scheduling,
        "agenda_for_day",
        side_effect=ValueError("no reminders store"),
    ):
        _, text = daily_brief.build_daily_brief(today=TODAY)

    assert "## Today" in text
    assert "_unavailable_" in text
    assert "agenda" in text  # named in the trailing unavailable note


def test_every_source_can_fail_without_crashing():
    from thursday import company_state

    sources = {
        "business_status": ("client", "business_status"),
        "company_state": (company_state, "get_snapshot"),
        "agenda": ("scheduling", "agenda_for_day"),
        "week_ahead": ("scheduling", "agenda_for_week"),
        "agent_receipts": ("action_receipts", "recent_receipts"),
        "scheduler": ("scheduler", "load_schedules"),
    }
    for section_name, (module_name, fn_name) in sources.items():
        module = (
            getattr(daily_brief, module_name)
            if isinstance(module_name, str)
            else module_name
        )
        with patch.object(module, fn_name, side_effect=OSError("boom")):
            brief = daily_brief.compose_daily_brief(today=TODAY)
            assert section_name in brief["summary"]["unavailable"]
            assert brief["sections"][section_name]["status"] == "unavailable"
            _, text = daily_brief.build_daily_brief(today=TODAY)
            assert text  # still renders


# ─── Handler integration ─────────────────────────────────────────────────


def test_calendar_handler_routes_briefing_to_composed_brief():
    from thursday.registry.handlers import _handle_calendar

    text = _handle_calendar("give me my daily briefing", {})
    assert "# Daily Brief" in text
    assert "## Today" in text
    assert "## Agent Activity" in text
    assert "Ready when you are." not in text


def test_calendar_handler_falls_back_when_all_sections_unavailable():
    from thursday.registry import handlers

    with patch.object(
        daily_brief.client, "business_status", side_effect=OSError("boom")
    ), patch.object(
        handlers.daily_brief, "compose_daily_brief"
    ) as compose:
        compose.return_value = {
            "generated_at": "2026-08-22T09:00:00",
            "today": TODAY.isoformat(),
            "sections": {
                name: {"status": "unavailable", "error": "boom"}
                for name in daily_brief.BRIEF_SECTIONS
            },
            "summary": {
                "available": [],
                "unavailable": list(daily_brief.BRIEF_SECTIONS),
                "total_sections": len(daily_brief.BRIEF_SECTIONS),
            },
        }
        text = handlers._handle_calendar("morning briefing", {})

    assert "## Today" in text  # legacy agenda still present
    assert text.strip()


def test_week_agenda_requests_do_not_trigger_composed_brief():
    from thursday.registry.handlers import _handle_calendar

    text = _handle_calendar("what does my week look like", {})
    assert "# Daily Brief" not in text


# ─── Empty state ─────────────────────────────────────────────────────────


def test_empty_state_renders_cleanly():
    # DEFAULT_SCHEDULES ships with entries; empty state means nothing due now.
    with patch.object(
        daily_brief.scheduler, "load_schedules", return_value={}
    ):
        brief, text = daily_brief.build_daily_brief(today=TODAY)

    assert brief["sections"]["agent_receipts"]["payload"] == []
    sched = brief["sections"]["scheduler"]["payload"]
    assert sched["registered"] == {
        "daily": 0,
        "weekly": 0,
        "monthly": 0,
    }
    assert sched["due_now"] == []
    assert "No agent actions in the last 24 hours." in text
    assert "No scheduled tasks registered." in text


# ─── Company state section ───────────────────────────────────────────────


@pytest.fixture()
def _company_db(tmp_path, monkeypatch):
    monkeypatch.setenv("THURSDAY_COMPANY_DB", str(tmp_path / "company.db"))
    from thursday import company_state

    company_state.invalidate_cache()
    yield
    company_state.invalidate_cache()


def test_company_section_renders_prioritised_state(_company_db):
    from nite_ai.company_store import open_store
    from nite_ai.domain import Goal, GoalKind, ItemStatus, Project, Task

    import time as time_module

    now = time_module.time()
    from thursday import company_state as _cs

    conn, store = open_store(_cs.db_path())
    g = store.create_goal(
        Goal(
            goal_id="g1", kind=GoalKind.COMPANY, title="Launch",
            status=ItemStatus.ACTIVE, progress=0.3,
            target_date_epoch=now - 86400,
        )
    )
    p = store.create_project(
        Project(
            project_id="p1", title="SLO", goal_id=g.goal_id,
            status=ItemStatus.ACTIVE, progress=0.4,
        )
    )
    store.create_task(
        Task(
            task_id="t1", title="Fix blocker bug", project_id=p.project_id,
            status=ItemStatus.BLOCKED, priority=8, blocked_by=("review",),
        )
    )
    store.create_task(
        Task(
            task_id="t2", title="Overdue paperwork", project_id=p.project_id,
            status=ItemStatus.ACTIVE, due_epoch=now - 500, priority=6,
        )
    )
    store.record_approval("ap-9", "high", "company.approvals.decide", "Send announcement")

    _, text = daily_brief.build_daily_brief(today=TODAY)
    assert "## Company State" in text
    assert "Blocked:" in text and "Fix blocker bug" in text and "review" in text
    assert "Overdue:" in text and "Overdue paperwork" in text
    assert "Needs your approval:" in text and "Send announcement" in text
    assert "Goals past target date:" in text
    conn.close()


def test_company_section_honest_empty_state(_company_db):
    _, text = daily_brief.build_daily_brief(today=TODAY)
    assert "## Company State" in text
    assert "No company state recorded yet" in text


def test_company_section_degrades_when_platform_missing(_company_db, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "nite_ai.company_store", None)
    monkeypatch.setitem(sys.modules, "nite_ai", None)
    _, text = daily_brief.build_daily_brief(today=TODAY)
    # Section degrades without crashing the whole brief.
    assert "## Company State" in text or "unavailable" in text.lower()
    assert "# Daily Brief" in text  # brief itself survives


def test_company_section_marks_stale_data(_company_db):
    from unittest.mock import patch

    from thursday import company_state

    snapshot = company_state.capture_snapshot()
    stale = company_state.CompanySnapshot(
        captured_at_epoch=snapshot.captured_at_epoch - 3600,
    )
    with patch.object(company_state, "get_snapshot", return_value=stale):
        _, text = daily_brief.build_daily_brief(today=TODAY)

    if "No company state recorded yet" not in text:
        assert "STALE" in text
