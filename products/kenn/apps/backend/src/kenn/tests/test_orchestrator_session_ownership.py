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


_RECIPE_REQUESTS = [
    ("rack_synthesizer", "build a neuro reese rack on track 1"),
    ("neural_midi_generator", "write a bouncy bassline in D minor"),
    ("surgical_masking_doctor", "fix the masking in my drop"),
]


@pytest.fixture
def isolated_recipe_dispatch(isolated_dispatch, monkeypatch):
    from kenn import mixing_doctor, plugin_handoff

    orchestrator, fake = isolated_dispatch
    calls = []

    def snapshot():
        calls.append("snapshot")
        return fake.query_session_state()

    def telemetry(session_id):
        calls.append(("telemetry", session_id))
        return None

    monkeypatch.setattr(mixing_doctor, "get_latest_session_state", snapshot)
    monkeypatch.setattr(plugin_handoff, "live_context_summary", telemetry)
    return orchestrator, fake, calls


@pytest.mark.parametrize("agent,query", _RECIPE_REQUESTS)
@pytest.mark.parametrize(
    "request_kwargs",
    [{}, {"session_id": None}, {"session_id": ""}, {"session_id": "   "},
     {"session_id": 7}, {"session_id": []}, {"session_id": "x" * 129}],
    ids=["omitted", "null", "empty", "blank", "number", "list", "overlong"],
)
def test_unbound_recipe_dispatch_stops_before_session_reads_or_proposal_work(
    isolated_recipe_dispatch, monkeypatch, agent, query, request_kwargs,
):
    # Recipe dispatch used shared owners or coerced invalid IDs before preparing changes.
    from kenn.core import generative_midi, rack_builder
    from kenn.core.session_doctor import SessionDoctor

    orchestrator, fake, calls = isolated_recipe_dispatch
    before_live = deepcopy(fake.query_session_state())

    def proposal_work(*args, **kwargs):
        calls.append("proposal_work")
        raise AssertionError("An unbound request must stop before proposal work")

    monkeypatch.setattr(rack_builder, "synthesize_rack_proposal", proposal_work)
    monkeypatch.setattr(generative_midi, "generate_audiogen_bassline", proposal_work)
    monkeypatch.setattr(SessionDoctor, "formulate_surgical_remediation_proposal", proposal_work)
    assert orchestrator.classify(query) == agent
    result = orchestrator.dispatch(query, **request_kwargs)
    assert result["status"] == "invalid"
    assert not result.get("proposal")
    assert not result.get("confirmation_token")
    assert not result["requires_confirmation"]
    assert calls == []
    assert not confirmation._ISSUED_TOKENS
    assert fake.query_session_state() == before_live


@pytest.mark.parametrize("agent,query", _RECIPE_REQUESTS)
@pytest.mark.parametrize("owners", [("recipe-a", "recipe-b"), ("  recipe-a  ", "x" * 128)])
def test_bound_recipe_dispatch_keeps_each_chats_proposal_owner_and_token_separate(
    isolated_recipe_dispatch, agent, query, owners,
):
    orchestrator, fake, calls = isolated_recipe_dispatch
    before_live = deepcopy(fake.query_session_state())
    results = [orchestrator.dispatch(query, session_id=owner) for owner in owners]
    for owner, result in zip(owners, results):
        assert result["agent_name"] == agent
        assert result["status"] == "confirmation_required"
        assert result["proposal"]["session_id"] == owner.strip()
        assert result["requires_confirmation"]
    assert results[0]["confirmation_token"] != results[1]["confirmation_token"]
    if agent == "surgical_masking_doctor":
        assert [call for call in calls if isinstance(call, tuple)] == [
            ("telemetry", owner.strip()) for owner in owners
        ]
    assert fake.query_session_state() == before_live


def test_anonymous_dispatch_can_list_racks_without_reading_the_live_session(isolated_recipe_dispatch):
    orchestrator, fake, calls = isolated_recipe_dispatch
    before_live = deepcopy(fake.query_session_state())
    result = orchestrator.dispatch("list available racks")
    assert result["agent_name"] == "rack_synthesizer"
    assert result["status"] == "catalog"
    assert result["racks"]
    assert not result.get("proposal")
    assert not result.get("confirmation_token")
    assert calls == []
    assert fake.query_session_state() == before_live
