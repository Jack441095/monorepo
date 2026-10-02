"""Writes made through the agent tools never reached the receipt journal, so Undo could not find them.

The HTTP routes journal every receipt; the autonomous tools returned theirs to the model and dropped it.
"""

from __future__ import annotations

import pytest

from kenn import autonomous_agent
from kenn.core import live_action_service, live_receipt_journal


class _Service:
    """Stands in for LiveActionService: one stored proposal, one canned execute result."""

    def __init__(self, proposal, result):
        self._proposal = proposal
        self._result = result

    def proposal_for_token(self, token):
        return self._proposal

    def execute(self, proposal, confirm_token, session_id):
        return self._result

    execute_device_action = execute


@pytest.fixture
def journal(monkeypatch):
    rows = []
    monkeypatch.setattr(
        live_receipt_journal, "record_receipt",
        lambda receipt, *, session_id="": rows.append((receipt, session_id)) or True,
    )
    return rows


def _serve(monkeypatch, proposal, result):
    monkeypatch.setattr(live_action_service, "LiveActionService", lambda: _Service(proposal, result))


def test_a_confirmed_track_write_is_journaled_under_its_session(monkeypatch, journal):
    receipt = {"receipt_id": "r1", "verified": True, "before": 0.4}
    _serve(monkeypatch,
           {"action": "set_volume", "track_index": 2, "after": 0.7},
           {"ok": True, "receipt": receipt})
    out = autonomous_agent._safe_track_action("set_volume", 2, 0.7, "tok", "s1")
    assert out["status"] == "success"
    assert journal == [(receipt, "s1")]


def test_a_failed_track_write_is_journaled_too(monkeypatch, journal):
    receipt = {"receipt_id": "r2", "verified": False}
    _serve(monkeypatch,
           {"action": "set_mute", "track_index": 1, "after": True},
           {"ok": False, "error": "readback differed", "receipt": receipt})
    out = autonomous_agent._safe_track_action("set_mute", 1, True, "tok", "s1")
    assert out["status"] == "failed"
    assert journal == [(receipt, "s1")]


def test_a_confirmed_transport_write_is_journaled(monkeypatch, journal):
    receipt = {"receipt_id": "r3", "verified": True}
    _serve(monkeypatch, {"action": "transport_play"}, {"ok": True, "receipt": receipt})
    out = autonomous_agent._safe_transport_action("transport_play", "tok", "s2")
    assert out["status"] == "success"
    assert journal == [(receipt, "s2")]


def test_a_confirmed_device_write_is_journaled(monkeypatch, journal):
    receipt = {"receipt_id": "r4", "verified": True}
    monkeypatch.setattr(autonomous_agent, "_daw_write_denied", lambda: None)
    _serve(monkeypatch,
           {"track_index": 0, "device_index": 1, "parameter_index": 3, "after": 0.5},
           {"ok": True, "receipt": receipt})
    out = autonomous_agent.tool_set_ableton_parameter(0, 1, 3, 0.5, confirm_token="tok", session_id="s3")
    assert out["status"] == "success"
    assert journal == [(receipt, "s3")]


def test_a_write_that_returns_no_receipt_journals_nothing(monkeypatch, journal):
    _serve(monkeypatch, {"action": "transport_stop"}, {"ok": False, "error": "refused"})
    autonomous_agent._safe_transport_action("transport_stop", "tok", "s2")
    assert journal == []


def test_a_token_for_a_different_action_is_not_executed_or_journaled(monkeypatch, journal):
    _serve(monkeypatch,
           {"action": "set_pan", "track_index": 2, "after": 0.7},
           {"ok": True, "receipt": {"receipt_id": "r5"}})
    out = autonomous_agent._safe_track_action("set_volume", 2, 0.7, "tok", "s1")
    assert out["status"] == "failed"
    assert journal == []
