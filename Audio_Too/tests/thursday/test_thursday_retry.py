"""Tests for thursday.retry — bounded retry/backoff for transient failures."""

from __future__ import annotations

import types

import pytest

from nite_core import PublicError, PublicErrorCode
from thursday import orchestrator
from thursday.registry import ActionRisk
from thursday.registry.core import ServiceDef
from thursday.retry import RetryPolicy, is_retryable, with_retry


def test_is_retryable_transient_exception_types():
    assert is_retryable(TimeoutError("timed out"))
    assert is_retryable(ConnectionError("dropped"))
    assert is_retryable(OSError("io error"))


def test_is_retryable_logic_errors_are_not_retried():
    assert not is_retryable(ValueError("bad input"))
    assert not is_retryable(KeyError("missing"))
    assert not is_retryable(TypeError("wrong type"))


def test_is_retryable_honors_public_error_flag():
    retryable_exc = PublicError(
        PublicErrorCode.SERVICE_UNAVAILABLE, "unavailable", retryable=True,
    )
    not_retryable_exc = PublicError(
        PublicErrorCode.PERMISSION_DENIED, "denied", retryable=False,
    )
    assert is_retryable(retryable_exc)
    assert not is_retryable(not_retryable_exc)


def test_with_retry_succeeds_after_transient_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("still warming up")
        return "ok"

    sleeps: list[float] = []
    result = with_retry(
        flaky,
        RetryPolicy(max_attempts=3, backoff_seconds=(0.1, 0.1)),
        sleep=sleeps.append,
    )

    assert result == "ok"
    assert calls["n"] == 3
    assert sleeps == [0.1, 0.1]


def test_with_retry_gives_up_after_max_attempts():
    calls = {"n": 0}

    def always_fails():
        calls["n"] += 1
        raise ConnectionError("never recovers")

    with pytest.raises(ConnectionError):
        with_retry(
            always_fails,
            RetryPolicy(max_attempts=2, backoff_seconds=(0.1,)),
            sleep=lambda _: None,
        )

    assert calls["n"] == 2


def test_with_retry_does_not_retry_non_transient_errors():
    calls = {"n": 0}

    def bad_input():
        calls["n"] += 1
        raise ValueError("garbage in")

    with pytest.raises(ValueError):
        with_retry(
            bad_input,
            RetryPolicy(max_attempts=3, backoff_seconds=(0.1, 0.1)),
            sleep=lambda _: None,
        )

    assert calls["n"] == 1


# ── Orchestrator-level: a retryable service error now succeeds on retry ────


def test_handle_retries_a_transient_service_error_and_succeeds(monkeypatch, tmp_path):
    """Before Phase 1, any exception from a service's action() surfaced
    immediately as ServiceExecutionError. A transient failure (e.g. a dropped
    connection) should now be retried in place and the turn should complete
    normally instead of erroring out."""
    from thursday import session_manager

    calls = {"n": 0}

    def flaky_action(ctx, api, text):
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("dropped mid-call")
        return "all good now"

    services = {"flaky": ServiceDef(name="Flaky", description="flaky test service", action=flaky_action)}

    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    monkeypatch.setenv("THURSDAY_CONFIRMATION_SECRET", "test-secret-with-enough-entropy")
    monkeypatch.setenv("THURSDAY_ACTION_RECEIPTS_DB", str(tmp_path / "receipts.sqlite3"))
    monkeypatch.setattr(orchestrator, "should_check", lambda *a, **k: False)
    monkeypatch.setattr(orchestrator, "get_pending_alerts", lambda *a, **k: [])
    monkeypatch.setattr(orchestrator, "request_risk", lambda *a, **k: ActionRisk.READ_ONLY)
    monkeypatch.setattr(orchestrator, "build_services", lambda api: services)

    intent = types.SimpleNamespace(name="contextual", entities={})
    brain_decision = types.SimpleNamespace(
        type="subagent", abstract="run flaky",
        steps=[{"kind": "service", "service_id": "flaky"}],
    )
    decision = orchestrator.RequestDecision(
        resolved_text="run flaky", resolved_entities={}, intent=intent,
        execution_target="brain", brain_decision=brain_decision,
    )
    monkeypatch.setattr(orchestrator, "classify_request", lambda text, session: decision)

    session = session_manager.get_or_create_session("retry-e2e")
    resp = orchestrator.handle("run flaky", session=session, list_records=lambda _n: [])

    assert calls["n"] == 2
    assert "all good now" in resp
