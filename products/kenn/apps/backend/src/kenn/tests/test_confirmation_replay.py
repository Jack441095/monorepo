import kenn.core.confirmation as confirmation
from kenn.core.confirmation import consume_confirmation, issue_confirmation


def test_confirmation_is_bound_and_single_use_for_mutations() -> None:
    token, _ = issue_confirmation(session_id="s", service_id="ableton", text="set:x=1")
    assert consume_confirmation(token, session_id="s", service_id="ableton", text="set:x=1") is True
    assert consume_confirmation(token, session_id="s", service_id="ableton", text="set:x=1") is False
    other, _ = issue_confirmation(session_id="s", service_id="ableton", text="set:x=2")
    assert consume_confirmation(other, session_id="s", service_id="ableton", text="set:x=1") is False


def test_confirmation_is_invalidated_when_process_secret_rotates(monkeypatch) -> None:
    monkeypatch.setenv("KENN_CONFIRMATION_SECRET", "stable-deployment-root")
    token, _ = confirmation.issue_confirmation(session_id="restart", service_id="ableton", text="set:x=1")
    monkeypatch.setattr(confirmation, "_PROCESS_SECRET", b"a-new-process-secret")
    assert confirmation.verify_confirmation(token, session_id="restart", service_id="ableton", text="set:x=1") is False
