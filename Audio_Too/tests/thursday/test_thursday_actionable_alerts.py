"""Actionable alerts (docs/THURSDAY_KENN_AGENT_PLAN_2026-07-20.md §5.4).

The proactive monitor already detects overdue invoices, flagged mix reviews,
finished renders, etc. and surfaces them as informational text. Now the
highest-severity actionable alert also offers a safe, read-only one-word
follow-up ("Reply 'yes' and I'll show your flagged mix review"). An affirmative
next turn runs the suggested command; the suggestion is one-shot (cleared
whether or not it's used) and an in-flight confirmation always takes precedence.
"""

from __future__ import annotations

import types


from thursday import orchestrator
from thursday import monitor
from thursday import session_manager


# ── monitor.top_actionable_suggestion (pure) ──────────────────────────────


def test_suggestion_prefers_highest_severity():
    alerts = [
        {"type": "new_enquiry", "severity": "info"},
        {"type": "overdue_invoice", "severity": "critical"},
    ]
    assert monitor.top_actionable_suggestion(alerts) == {
        "command": "show invoices",
        "label": "show your overdue invoices",
    }


def test_suggestion_none_when_no_actionable_alert():
    assert monitor.top_actionable_suggestion([{"type": "expiring_link", "severity": "warning"}]) is None
    assert monitor.top_actionable_suggestion([]) is None


# ── handle() integration ──────────────────────────────────────────────────


def _setup(monkeypatch, tmp_path, *, pending_alerts, classify):
    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    monkeypatch.setattr(orchestrator, "should_check", lambda *a, **k: False)
    monkeypatch.setattr(orchestrator, "get_pending_alerts", lambda *a, **k: pending_alerts)
    monkeypatch.setattr(orchestrator, "classify_request", classify)


def _chat_decision(text):
    intent = types.SimpleNamespace(name="contextual", entities={})
    bd = types.SimpleNamespace(
        type="chat", abstract=f"RAN:{text.strip()}", message=f"RAN:{text.strip()}", steps=[]
    )
    return orchestrator.RequestDecision(text, {}, intent, "brain", bd)


def test_actionable_alert_stores_a_pending_suggestion(monkeypatch, tmp_path):
    alerts = [{"id": "1", "type": "mix_review_flagged", "severity": "warning", "message": "1 flagged"}]
    _setup(monkeypatch, tmp_path, pending_alerts=alerts, classify=lambda t, s: _chat_decision(t))
    session = session_manager.get_or_create_session("offer")

    orchestrator.handle("hello", session=session, list_records=lambda _n: [])

    assert session["context"]["pending_suggestion"] == {
        "command": "list mix reviews",
        "label": "show your flagged mix review",
    }


def test_yes_runs_the_suggested_command_and_clears_it(monkeypatch, tmp_path):
    # No new alerts this turn; a suggestion is already pending from last turn.
    _setup(monkeypatch, tmp_path, pending_alerts=[], classify=lambda t, s: _chat_decision(t))
    session = session_manager.get_or_create_session("consume")
    session_manager.update_context(session, {
        "pending_suggestion": {"command": "list mix reviews", "label": "show your flagged mix review"},
    })

    resp = orchestrator.handle("yes", session=session, list_records=lambda _n: [])

    assert "RAN:list mix reviews" in resp  # the suggested command actually ran
    assert session["context"]["pending_suggestion"] is None  # one-shot: cleared


def test_non_affirmative_reply_clears_suggestion_without_running_it(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, pending_alerts=[], classify=lambda t, s: _chat_decision(t))
    session = session_manager.get_or_create_session("clear")
    session_manager.update_context(session, {
        "pending_suggestion": {"command": "list mix reviews", "label": "show your flagged mix review"},
    })

    resp = orchestrator.handle("what's my pipeline", session=session, list_records=lambda _n: [])

    assert "RAN:what's my pipeline" in resp  # the user's actual request ran, not the suggestion
    assert "list mix reviews" not in resp
    assert session["context"]["pending_suggestion"] is None  # one-shot: cleared regardless


def test_pending_confirmation_takes_precedence_over_suggestion(monkeypatch, tmp_path):
    """If there's an in-flight confirmation AND a pending suggestion, 'yes'
    confirms the action; it does not run the suggestion."""
    _setup(monkeypatch, tmp_path, pending_alerts=[], classify=lambda t, s: _chat_decision(t))
    session = session_manager.get_or_create_session("precedence")
    session_manager.update_context(session, {
        "pending_confirmation": {"token": "v1.deadbeef.aa.bb", "text": "x", "service_id": "svc"},
        "pending_suggestion": {"command": "list mix reviews", "label": "show your flagged mix review"},
    })

    resp = orchestrator.handle("yes", session=session, list_records=lambda _n: [])

    # 'yes' was routed to the confirmation path (an invalid/expired token here),
    # NOT to the suggested command.
    assert "RAN:list mix reviews" not in resp
    assert session["context"]["pending_suggestion"] is None  # still cleared (one-shot)
