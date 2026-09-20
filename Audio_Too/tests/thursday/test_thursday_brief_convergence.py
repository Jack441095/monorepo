"""Briefing convergence parity tests (V2-A §17–18).

The canonical composer (`thursday/daily_brief.py`) must not lose any
semantic element the legacy `scheduling.daily_briefing` provided on text
surfaces: greeting, date line, agenda content, pending alerts, closing.

The watcher's voice surface keeps a speech-optimised one-liner by design
(markdown headers must not be spoken) — documented deliberate difference.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from thursday import daily_brief, scheduling


TODAY = None  # conversational mode uses real clock; content assertions are structural


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("THURSDAY_COMPANY_DB", str(tmp_path / "company.db"))
    monkeypatch.setattr(
        daily_brief.scheduling, "REMINDERS_FILE", tmp_path / "reminders.json"
    )
    from thursday import company_state

    company_state.invalidate_cache()
    yield
    company_state.invalidate_cache()


def _legacy_elements(list_records=None):
    text = scheduling.daily_briefing(list_records)
    return {
        "greeting_line": text.splitlines()[0],
        "has_date": "Today is" in text,
        "has_agenda": "Agenda for" in text or "No reminders" in text,
        "closing": "Ready when you are." in text,
    }


def test_conversational_composed_brief_covers_legacy_semantics():
    legacy = _legacy_elements()

    _, composed = daily_brief.build_daily_brief(conversational=True)

    # Greeting shape: time-based salutation.
    first = composed.splitlines()[0]
    assert any(
        first.startswith(g)
        for g in ("Good morning", "Good afternoon", "Good evening")
    ), first

    # Date line present like legacy.
    assert "Today is" in composed
    # Agenda section present (composed renders it under "## Today").
    assert "## Today" in composed or "Agenda for" in composed
    # Legacy closing retained.
    assert "Ready when you are." in composed
    # And everything legacy had structurally:
    assert legacy["has_agenda"]  # sanity: legacy fixture behaves


def test_conversational_brief_surfaces_pending_alerts():
    alerts = [
        {"message": "Invoice INV-77 overdue"},
        {"message": "KENN retraining finished"},
    ]
    with patch(
        "thursday.monitor.get_pending_alerts", return_value=alerts
    ):
        _, text = daily_brief.build_daily_brief(conversational=True)

    assert "2 pending alert(s)" in text
    assert "Invoice INV-77 overdue" in text
    assert "KENN retraining finished" in text


def test_conversational_brief_greets_by_name():
    _, text = daily_brief.build_daily_brief(conversational=True, user_name="Jack")
    first = text.splitlines()[0]
    assert first.startswith("Good ") and ", Jack." in first


def test_plain_mode_has_no_chatter():
    """Non-conversational consumers (handler requests) stay clean markdown."""
    _, text = daily_brief.build_daily_brief()
    assert not text.startswith("Good ")
    assert "Ready when you are." not in text
    assert "# Daily Brief" in text
