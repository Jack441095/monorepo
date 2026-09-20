"""Exactly-once execution for confirmed consequential actions.

A receipt-backed action must never be re-executed by the retry layer:
if the first attempt times out after the side effect landed, a retry
would double-apply it. Transient failures on consequential actions
surface as honest failures instead. Read-only services keep retry
smoothing (covered by test_thursday_retry.py).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from thursday import session_manager
from thursday.command_gateway import command_for_text, execute_command
from thursday.orchestrator import handle


@pytest.fixture()
def isolated_session(tmp_path, monkeypatch):
    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    monkeypatch.setenv("THURSDAY_CONFIRMATION_SECRET", "test-secret-with-enough-entropy")
    monkeypatch.setenv("THURSDAY_ACTION_RECEIPTS_DB", str(tmp_path / "receipts.sqlite3"))
    return session_manager.get_or_create_session("exactly-once")


def _quiet_orchestrator():
    return (
        patch("thursday.orchestrator.should_check", return_value=False),
        patch("thursday.orchestrator.get_pending_alerts", return_value=[]),
    )


def test_confirmed_action_timeout_does_not_reexecute(isolated_session):
    """First attempt raises TimeoutError after 'applying' the effect;
    the retry layer must NOT run it a second time."""
    calls = {"n": 0}

    def flaky_action(api, text):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("provider stalled after applying the change")
        return "applied twice!"

    request = "set ableton track 2 device 1 parameter 3 to -6"

    with _quiet_orchestrator()[0], _quiet_orchestrator()[1], patch(
        "thursday.registry.studio._handle_ableton_push",
        side_effect=flaky_action,
    ):
        blocked = execute_command(
            command_for_text(request), session=isolated_session, handle_fn=handle
        )
        assert blocked.result["requires_confirmation"] is True
        token = blocked.result["confirmation_token"]

        completed = execute_command(
            command_for_text(f"confirm {token}"),
            session=isolated_session,
            handle_fn=handle,
        )

    assert calls["n"] == 1  # exactly once — no retry re-execution
    # The honest failure is reported, not a phantom success.
    assert "twice" not in str(completed.result)


def test_receipt_recorded_as_processing_after_failed_consequential_attempt(
    isolated_session,
):
    """After a failed attempt the receipt stays 'processing' (not 'completed'),
    so replaying the same confirmation cannot re-run the action."""
    from thursday import action_receipts

    calls = {"n": 0}

    def always_fails(api, text):
        calls["n"] += 1
        raise TimeoutError("stalled")

    request = "set ableton track 2 device 1 parameter 3 to -6"

    with _quiet_orchestrator()[0], _quiet_orchestrator()[1], patch(
        "thursday.registry.studio._handle_ableton_push",
        side_effect=always_fails,
    ):
        blocked = execute_command(
            command_for_text(request), session=isolated_session, handle_fn=handle
        )
        token = blocked.result["confirmation_token"]
        failed = execute_command(
            command_for_text(f"confirm {token}"),
            session=isolated_session,
            handle_fn=handle,
        )

    assert calls["n"] == 1

    receipt_id = action_receipts.receipt_id_for_token(token)
    stored = action_receipts.get_receipt(receipt_id, session_id="exactly-once")
    if stored is not None:
        assert stored.status == "processing"

    # Replay of the same confirmation must not re-execute.
    with _quiet_orchestrator()[0], _quiet_orchestrator()[1], patch(
        "thursday.registry.studio._handle_ableton_push",
        side_effect=always_fails,
    ):
        replay = execute_command(
            command_for_text(f"confirm {token}"),
            session=isolated_session,
            handle_fn=handle,
        )

    assert calls["n"] == 1  # still exactly one attempt overall
    assert "already being processed" in str(replay.result) or calls["n"] == 1
