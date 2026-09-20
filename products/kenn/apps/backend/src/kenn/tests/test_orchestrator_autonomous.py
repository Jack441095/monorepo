"""Tests for KENN Orchestrator Autonomous Producer Sub-Agent Integration."""

import pytest
from kenn.orchestrator import KennOrchestrator, get_orchestrator


@pytest.fixture
def orchestrator():
    return KennOrchestrator()


@pytest.fixture
def mock_clashing_session():
    return {
        "status": "connected",
        "tracks": [
            {"index": 0, "name": "Kick", "volume": 0.88, "pan": 0.0, "panning": 0.0, "devices": []},
            {"index": 1, "name": "Sub Bass", "volume": 0.85, "pan": 0.25, "panning": 0.25, "devices": []},
            {"index": 2, "name": "Lead Vocal", "volume": 0.70, "pan": 0.0, "panning": 0.0, "devices": []},
            {"index": 3, "name": "Supersaw Synth", "volume": 0.80, "pan": 0.0, "panning": 0.0, "devices": []},
        ],
    }


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


def test_orchestrator_dispatch_autonomous_producer(orchestrator, mock_clashing_session):
    result = orchestrator.dispatch(
        "rebalance the mix and solve clashes",
        session_snapshot=mock_clashing_session,
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
    assert result["confirmation_token"].startswith("react_")

    # Verify ReAct trajectory is present
    assert "trajectory" in result
    phases = [step["phase"] for step in result["trajectory"]]
    assert "perception" in phases
    assert "diagnosis" in phases
    assert "synthesis" in phases

