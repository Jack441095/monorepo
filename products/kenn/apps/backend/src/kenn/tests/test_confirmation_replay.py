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


def test_confirmation_accepts_browser_json_number_formatting() -> None:
    from kenn.core.actions.common import _text

    server = {"action": "set_pan", "track_index": 5, "track_name": "Synth",
              "before": 0.0, "after": -1.0, "session_version": "9a933ea042f5"}
    browser = {**server, "before": 0, "after": -1}  # JSON.stringify drops ".0"
    token, _ = issue_confirmation(session_id="s", service_id="ableton_action", text=_text(server))
    assert consume_confirmation(token, session_id="s", service_id="ableton_action", text=_text(browser))
    assert not consume_confirmation(token, session_id="s", service_id="ableton_action", text=_text(browser))


def test_confirmation_number_canonicalisation_keeps_values_bound() -> None:
    base = "set_volume|2|Bass|0.5|0.75|abc123"
    token, _ = issue_confirmation(session_id="s", service_id="ableton_action", text=base)
    assert not consume_confirmation(token, session_id="s", service_id="ableton_action", text="set_volume|2|Bass|0.5|0.8|abc123")
    assert not consume_confirmation(token, session_id="s", service_id="ableton_action", text="set_volume|3|Bass|0.5|0.75|abc123")
    assert not consume_confirmation(token, session_id="s", service_id="ableton_action", text="set_volume|2|Bass|0.5|0.75|abc124")
    assert not consume_confirmation(token, session_id="other", service_id="ableton_action", text=base)
    small, _ = issue_confirmation(session_id="s", service_id="ableton_action", text="gain|1e-05|-0.0")
    assert consume_confirmation(small, session_id="s", service_id="ableton_action", text="gain|0.00001|0")
