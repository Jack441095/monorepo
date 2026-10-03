from collections import OrderedDict
from copy import deepcopy

import pytest

from kenn.core import confirmation, live_action_service, live_command, session_context
from kenn.core.fake_live import FakeLiveBackend
from kenn.orchestrator import KennOrchestrator


@pytest.fixture
def isolated_dispatch(monkeypatch):
    fake = FakeLiveBackend()
    monkeypatch.setattr(live_action_service, "live_client", fake)
    monkeypatch.setattr(session_context, "_LIVE_CONVERSATIONS", OrderedDict())
    monkeypatch.setattr(confirmation, "_USED_TOKENS", set())
    monkeypatch.setattr(confirmation, "_ISSUED_TOKENS", {})
    monkeypatch.setattr(confirmation, "_REVOKED_TOKENS", set())
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setenv("KENN_LLM_ENABLED", "0")
    return KennOrchestrator(), fake


@pytest.mark.parametrize("session_id", [None, "", "   ", 7, "x" * 129])
def test_unbound_live_dispatch_cannot_join_a_named_chats_proposals_or_history(isolated_dispatch, session_id):
    # Anonymous writes used the same invented owner as an explicitly named chat.
    orchestrator, fake = isolated_dispatch
    owner = "orchestrated-live"
    prepared = live_command.handle_command("mute track 1", session_id=owner, allow_llm=False)
    assert prepared["status"] == "confirmation_required"
    before_context = session_context.live_conversation_context(owner)
    before_tokens = dict(confirmation._ISSUED_TOKENS)
    before_live = deepcopy(fake.query_session_state())

    for query in ("mute track 2", "solo track 1"):
        result = orchestrator.dispatch(query, session_id=session_id)
        assert result["status"] == "invalid"
        assert not result.get("proposal")
        assert not result.get("confirmation_token")
        assert not result["requires_confirmation"]

    assert session_context.live_conversation_context(owner) == before_context
    assert confirmation._ISSUED_TOKENS == before_tokens
    assert set(session_context._LIVE_CONVERSATIONS) == {owner}
    assert fake.query_session_state() == before_live


@pytest.mark.parametrize("session_id", [None, "", "   ", 7, "x" * 129])
def test_unbound_producer_dispatch_stops_before_deliberation_or_calibration(isolated_dispatch, monkeypatch, session_id):
    # Deliberation recorded calibration and proposals under a shared invented owner.
    from kenn.autonomous_agent import KennAutonomousAgent

    calls = []
    monkeypatch.setattr(KennAutonomousAgent, "react_deliberate", lambda self, **kwargs: calls.append(kwargs) or {"ok": True})
    orchestrator, _ = isolated_dispatch
    for query in ("rebalance the mix", "resolve masking and clashes"):
        result = orchestrator.dispatch(query, session_id=session_id)
        assert result["status"] == "invalid"
        assert not result.get("proposal")
        assert not result.get("confirmation_token")
        assert not result["requires_confirmation"]
    assert calls == []


def test_bound_live_dispatch_keeps_each_chats_history_and_pending_tokens_separate(isolated_dispatch):
    orchestrator, _ = isolated_dispatch
    for owner, query in (("live-a", "mute track 1"), ("live-b", "solo track 2")):
        result = orchestrator.dispatch(query, session_id=owner)
        assert result["status"] == "confirmation_required"
        assert result["result"]["session_id"] == owner
        assert confirmation.pending_confirmation_count(session_id=owner) == 1
        assert session_context.live_conversation_context(owner)["last_command"] == query
    assert set(session_context._LIVE_CONVERSATIONS) == {"live-a", "live-b"}
    assert confirmation.pending_confirmation_count(session_id="orchestrated-live") == 0


@pytest.mark.parametrize("owner", ["producer-a", "producer-b", "orchestrated-producer"])
def test_bound_producer_dispatch_forwards_the_exact_chat_owner(isolated_dispatch, monkeypatch, owner):
    from kenn.autonomous_agent import KennAutonomousAgent

    calls = []
    monkeypatch.setattr(KennAutonomousAgent, "react_deliberate", lambda self, **kwargs: calls.append(kwargs) or {"ok": True})
    orchestrator, _ = isolated_dispatch
    result = orchestrator.dispatch("rebalance the mix", session_id=owner)
    assert result["status"] == "completed"
    assert calls[0]["session_id"] == owner


def test_anonymous_dispatch_can_still_inspect_the_live_session(isolated_dispatch, monkeypatch):
    import kenn.autonomous_agent as autonomous_agent

    orchestrator, fake = isolated_dispatch
    monkeypatch.setattr(autonomous_agent, "tool_query_ableton_session", fake.query_session_state)
    result = orchestrator.dispatch("show my session")
    assert result["status"] == "connected"
    assert result["result"]["tracks"]
    assert not confirmation._ISSUED_TOKENS
