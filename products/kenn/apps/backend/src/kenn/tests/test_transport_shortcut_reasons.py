"""Typing "play" while Live was unusable always answered "not reachable on OSC port 11000".

That was wrong whenever Live was up but gave no usable snapshot, and it hard-coded a port. The shortcut now
repeats the reason the action service gave.
"""

import pytest

from kenn.core import chat_answer, live_action_service, project_memory_advisory


class _Service:
    def __init__(self, reply):
        self.reply = reply
        self.asked = []

    def propose_transport_action(self, action, session_id=""):
        self.asked.append((action, session_id))
        return self.reply


@pytest.fixture
def serve(monkeypatch):
    monkeypatch.setattr(project_memory_advisory, "evaluate_memory_chat_intent", lambda *a, **k: None)

    def install(reply):
        service = _Service(reply)
        monkeypatch.setattr(live_action_service, "LiveActionService", lambda: service)
        return service

    return install


@pytest.mark.parametrize("query, action", [("play", "transport_play"), ("stop", "transport_stop")])
def test_a_refusal_repeats_the_services_reason_and_names_no_port(serve, query, action):
    service = serve({"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."})
    reply = chat_answer._short_circuit_evaluator(query, session_id="s1")
    assert "returned no usable snapshot" in reply["answer"]
    assert "11000" not in reply["answer"]
    assert reply["requires_confirmation"] is False and "proposal" not in reply
    assert service.asked == [(action, "s1")]


@pytest.mark.parametrize("query, verb", [("play", "start"), ("pause", "stop")])
def test_an_accepted_proposal_still_asks_for_confirmation(serve, query, verb):
    proposal = {"action": "x", "confirmation_token": "tok"}
    serve({"ok": True, "proposal": proposal})
    reply = chat_answer._short_circuit_evaluator(query, session_id="s1")
    assert reply["requires_confirmation"] is True and reply["confirmation_token"] == "tok"
    assert reply["proposal"] == proposal and verb in reply["answer"]
