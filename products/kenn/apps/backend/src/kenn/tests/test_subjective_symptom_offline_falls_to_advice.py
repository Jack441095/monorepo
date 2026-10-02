"""A buried-vocal complaint with Live offline got "I cannot control Ableton" instead of mix advice.

The subjective translator matches symptom wording as well as commands; with no
Live snapshot the orchestrator answered the symptom with a control error.
"""

from __future__ import annotations

from kenn import orchestrator
from kenn.core import live_command


def _offline(monkeypatch):
    monkeypatch.setattr(
        live_command, "handle_command",
        lambda query, **kw: {"status": "offline", "answer": "I cannot control Ableton until the AbletonOSC-backed KENN companion returns a fresh Live snapshot."},
    )


def test_a_symptom_report_with_live_offline_is_not_answered_as_a_control_error(monkeypatch):
    _offline(monkeypatch)
    out = orchestrator._dispatch_ableton(query="My vocal is buried in the chorus.", session_id="s1")
    assert out is None


def test_an_explicit_write_with_live_offline_still_says_live_is_offline(monkeypatch):
    _offline(monkeypatch)
    out = orchestrator._dispatch_ableton(query="Mute the vocal track", session_id="s1")
    assert out["status"] == "offline"
    assert "cannot control Ableton" in out["message"]


def test_a_symptom_report_with_live_connected_still_reaches_the_command_gateway(monkeypatch):
    monkeypatch.setattr(
        live_command, "handle_command",
        lambda query, **kw: {"status": "confirmation_required", "answer": "Raise the vocal 1.5 dB?", "confirmation_required": True},
    )
    out = orchestrator._dispatch_ableton(query="My vocal is buried in the chorus.", session_id="s1")
    assert out["requires_confirmation"] is True
