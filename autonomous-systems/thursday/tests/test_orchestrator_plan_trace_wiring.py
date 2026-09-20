"""Tests for thursday/orchestrator.py's execution-feedback-loop wiring:
_record_plan_trace's new keyword forwarding + return value, and
_attach_plan_id_to_feedback_state's interaction with session_manager.add_turn.
No prior test file touched this integration at all.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from thursday import orchestrator as orch
from thursday import session_manager as sm
from thursday.session_manager import _empty_session, add_turn


@pytest.fixture(autouse=True)
def _isolated_session_dir(tmp_path, monkeypatch):
    # add_turn() calls session_manager._save_session() internally -- isolate
    # it to a temp dir so these tests never touch a real installation's
    # session files.
    monkeypatch.setattr(sm, "SESSION_DIR", tmp_path)
    yield


def _brain_decision(**kw):
    defaults = dict(
        type="plan", abstract="do the thing", steps=[{"kind": "service", "service_id": "kenn", "params": {}}],
        confidence="high", question_for_user=None, message=None, raw_step_count=1,
        provider="mlx_lm", model="qwen3.5-4b", latency_s=4.2, failure_reason=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def test_record_plan_trace_forwards_model_metadata():
    bd = _brain_decision()
    with patch("thursday.plan_memory.save_plan_trace", return_value="plan-123") as mock_save:
        result = orch._record_plan_trace(
            text="check business status", brain_decision=bd, service_id="business_status", status="success",
        )
    assert result == "plan-123"
    _, kwargs = mock_save.call_args
    assert kwargs["provider"] == "mlx_lm"
    assert kwargs["model"] == "qwen3.5-4b"
    assert kwargs["confidence"] == "high"
    assert kwargs["latency_s"] == 4.2
    assert kwargs["raw_step_count"] == 1
    assert kwargs["decision_type"] == "plan"


def test_record_plan_trace_failure_reason_override_wins_over_brain_decision():
    bd = _brain_decision(failure_reason=None)
    with patch("thursday.plan_memory.save_plan_trace", return_value="plan-456") as mock_save:
        orch._record_plan_trace(
            text="x", brain_decision=bd, service_id="kenn", status="failed",
            failure_reason="service_exception",
        )
    _, kwargs = mock_save.call_args
    assert kwargs["failure_reason"] == "service_exception"


def test_record_plan_trace_no_service_id_produces_empty_executed_steps():
    bd = _brain_decision(type="chat", steps=[])
    with patch("thursday.plan_memory.save_plan_trace", return_value="plan-789") as mock_save:
        orch._record_plan_trace(text="hi", brain_decision=bd, service_id=None, status="chat")
    _, kwargs = mock_save.call_args
    assert kwargs["executed_steps"] == []
    assert kwargs["service_id"] is None


def test_record_plan_trace_returns_none_on_save_failure():
    bd = _brain_decision()
    with patch("thursday.plan_memory.save_plan_trace", side_effect=RuntimeError("db exploded")):
        result = orch._record_plan_trace(text="x", brain_decision=bd, service_id="kenn", status="success")
    assert result is None


def test_attach_plan_id_stamps_feedback_state_after_add_turn():
    session = _empty_session("test-session-1")
    add_turn(session, "thursday", "here's your answer", "chat", None, {})
    assert "plan_id" not in session["feedback_state"]

    orch._attach_plan_id_to_feedback_state(session, "plan-abc")
    assert session["feedback_state"]["plan_id"] == "plan-abc"


def test_attach_plan_id_is_noop_when_plan_id_is_none():
    session = _empty_session("test-session-1")
    add_turn(session, "thursday", "here's your answer", "chat", None, {})
    orch._attach_plan_id_to_feedback_state(session, None)
    assert "plan_id" not in session["feedback_state"]


def test_attach_plan_id_noop_on_malformed_feedback_state():
    session = {"feedback_state": "not-a-dict"}
    orch._attach_plan_id_to_feedback_state(session, "plan-abc")  # must not raise
    assert session["feedback_state"] == "not-a-dict"
