"""Tests for KENN Orchestrator Autonomous Producer Sub-Agent Integration."""

from copy import deepcopy

import pytest
from kenn.core import confirmation
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_recipe import LiveRecipeService, MAX_RECIPE_STEPS
from kenn.orchestrator import KennOrchestrator, get_orchestrator


@pytest.fixture
def orchestrator():
    return KennOrchestrator()


def test_autonomous_producer_subagent_registered(orchestrator):
    agent = orchestrator.agents.get("autonomous_producer")
    assert agent is not None
    assert agent.name == "autonomous_producer"
    assert agent.emoji == "🧠"
    assert "Multi-step ReAct deliberation" in agent.capabilities
    assert "Closed-loop acoustic calibration" in agent.capabilities


def test_orchestrator_classification_autonomous_producer(orchestrator):
    assert orchestrator.classify("balance the mix") == "autonomous_producer"
    assert orchestrator.classify("rebalance the session tracks") == "autonomous_producer"
    assert orchestrator.classify("run autonomous mix") == "autonomous_producer"
    assert orchestrator.classify("fix the mix") == "autonomous_producer"
    assert orchestrator.classify("resolve masking and clashes") == "autonomous_producer"
    assert orchestrator.classify("level the mix") == "autonomous_producer"


def test_orchestrator_informational_questions_bypassed(orchestrator):
    # Genuine informational questions should NOT be captured as imperative dispatch requests
    assert orchestrator.classify("how do I balance the mix?") is None
    assert orchestrator.classify("what is the best way to balance tracks?") is None
    assert orchestrator.classify("why is my mix clashing?") is None


def test_orchestrator_dispatch_autonomous_producer(orchestrator, fake_live):
    result = orchestrator.dispatch(
        "rebalance the mix and solve clashes",
        session_snapshot=fake_live.query_session_state(),
        session_id="test-orch-producer",
    )

    assert result is not None
    assert result["orchestrated"] is True
    assert result["agent_name"] == "autonomous_producer"
    assert result["agent_emoji"] == "🧠"
    assert "agent_envelope" in result
    assert result["status"] == "confirmation_required"
    assert result["requires_confirmation"] is True
    assert "proposal" in result
    assert result["proposal"]["schema"] == "kenn.ableton_recipe_proposal.v1"
    assert len(result["proposal"]["steps"]) > 0
    assert result["confirmation_token"].startswith("v1.")

    # Verify ReAct trajectory is present
    assert "trajectory" in result
    phases = [step["phase"] for step in result["trajectory"]]
    assert "perception" in phases
    assert "diagnosis" in phases
    assert "synthesis" in phases


def _prepare(fake, session_id="owner"):
    # Same fixture session the recipe is proposed against, so track identities line up.
    return KennOrchestrator().dispatch(
        "rebalance the mix and solve clashes",
        session_snapshot=fake.query_session_state(),
        session_id=session_id,
    )


def _volumes(fake):
    return {t["index"]: t["volume"] for t in fake.query_session_state()["tracks"]}


def test_an_autonomous_proposal_carries_a_token_the_confirmation_service_issued(fake_live):
    # It used to hand out react_<hash>, which nothing registered, so Apply and Dismiss could never find it.
    result = _prepare(fake_live)

    assert result["status"] == "confirmation_required"
    assert result["confirmation_token"].startswith("v1.")
    assert result["proposal"]["confirmation_token"] == result["confirmation_token"]
    assert confirmation.pending_confirmation_count(session_id="owner") == 1
    assert 1 <= len(result["proposal"]["steps"]) <= MAX_RECIPE_STEPS


def test_preparing_an_autonomous_proposal_does_not_write_to_live(fake_live):
    before = deepcopy(fake_live.query_session_state())
    _prepare(fake_live)
    assert fake_live.query_session_state() == before


def test_dismissing_an_autonomous_proposal_stops_a_held_copy_from_applying(fake_live):
    proposal = _prepare(fake_live)["proposal"]
    before = _volumes(fake_live)

    assert confirmation.revoke_confirmation(proposal["confirmation_token"], session_id="owner")
    result = LiveRecipeService(LiveActionService(fake_live)).execute_recipe(
        deepcopy(proposal), confirm_token=proposal["confirmation_token"], session_id="owner",
    )

    assert result["ok"] is False
    assert _volumes(fake_live) == before


def test_another_chat_cannot_dismiss_or_apply_an_autonomous_proposal(fake_live):
    proposal = _prepare(fake_live)["proposal"]
    before = _volumes(fake_live)

    assert not confirmation.revoke_confirmation(proposal["confirmation_token"], session_id="intruder")
    result = LiveRecipeService(LiveActionService(fake_live)).execute_recipe(
        deepcopy(proposal), confirm_token=proposal["confirmation_token"], session_id="intruder",
    )

    assert result["ok"] is False
    assert _volumes(fake_live) == before
    assert confirmation.pending_confirmation_count(session_id="owner") == 1


def test_an_edited_autonomous_proposal_is_refused(fake_live):
    proposal = deepcopy(_prepare(fake_live)["proposal"])
    proposal["steps"][0]["after"] = 0.99
    before = _volumes(fake_live)

    result = LiveRecipeService(LiveActionService(fake_live)).execute_recipe(
        proposal, confirm_token=proposal["confirmation_token"], session_id="owner",
    )

    assert result["ok"] is False
    assert _volumes(fake_live) == before


def test_a_confirmed_autonomous_proposal_applies_once_and_can_be_undone(fake_live):
    proposal = deepcopy(_prepare(fake_live)["proposal"])
    service = LiveRecipeService(LiveActionService(fake_live))
    before = _volumes(fake_live)

    applied = service.execute_recipe(proposal, confirm_token=proposal["confirmation_token"], session_id="owner")
    assert applied["ok"] is True and applied["receipt"]["verified"] is True
    after = _volumes(fake_live)
    for step in proposal["steps"]:
        assert after[step["track_index"]] == pytest.approx(step["after"], abs=1e-3)

    replay = service.execute_recipe(
        deepcopy(proposal), confirm_token=proposal["confirmation_token"], session_id="owner", idempotency_key="again",
    )
    assert replay["ok"] is False

    undo = service.propose_undo(applied["receipt"], session_id="owner")
    assert undo["ok"] is True
    restored = service.execute_recipe(
        undo["proposal"], confirm_token=undo["proposal"]["confirmation_token"], session_id="owner",
    )
    assert restored["ok"] is True
    assert _volumes(fake_live) == pytest.approx(before, abs=1e-3)


def test_steps_a_recipe_cannot_carry_are_reported_not_dropped(fake_live):
    result = _prepare(fake_live)

    left_out = result["result"]["left_out"]
    assert left_out, "the fixture session suggests more than one recipe can hold"
    assert all(item["reason"] for item in left_out)
    assert "Not included" in result["message"]
    carried = len(result["proposal"]["steps"])
    assert carried + len(left_out) == result["result"]["suggested_step_count"]


def test_an_unusable_suggestion_never_gets_a_confirmation_token():
    from kenn.autonomous_agent import _split_recipe_steps

    chosen, left_out = _split_recipe_steps([
        {"action": "insert_device", "track_index": 0, "track_name": "Kick"},
        {"action": "set_device_parameter", "track_name": "Master", "device_name": "Limiter", "after": -1.0},
        {"action": "set_volume", "track_index": 2, "track_name": "Hi-Hats", "before": 0.5},
    ])

    assert chosen == []
    assert [item["action"] for item in left_out] == ["insert_device", "set_device_parameter", "set_volume"]
    assert all(item["reason"] for item in left_out)


def test_two_suggestions_for_one_target_do_not_both_reach_the_recipe():
    from kenn.autonomous_agent import _split_recipe_steps

    first = {"action": "set_volume", "track_index": 0, "track_name": "Kick", "before": 0.5, "after": 0.43}
    again = {"action": "set_volume", "track_index": 0, "track_name": "Kick", "before": 0.5, "after": 0.40}
    other = {"action": "set_volume", "track_index": 1, "track_name": "Snare", "before": 0.5, "after": 0.55}

    chosen, left_out = _split_recipe_steps([first, again, other])

    assert chosen == [first, other]
    assert [item["track_name"] for item in left_out] == ["Kick"]
