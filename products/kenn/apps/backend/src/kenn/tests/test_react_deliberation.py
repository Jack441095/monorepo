"""Tests for KENN Multi-Step ReAct Autonomous Reasoning Engine."""

import pytest
from kenn.autonomous_agent import KennAutonomousAgent


def test_react_deliberate_formulates_unmasking_recipe(fake_live):
    agent = KennAutonomousAgent()
    result = agent.react_deliberate(
        "Make the vocal cut through and clean up low-end mud",
        session_id="test-react-session",
        session_snapshot=fake_live.query_session_state(),
    )

    assert result["ok"] is True
    assert result["status"] == "confirmation_required"
    assert result["confirmation_required"] is True
    assert "proposal" in result
    assert result["proposal"]["schema"] == "kenn.ableton_recipe_proposal.v1"
    assert len(result["proposal"]["steps"]) > 0

    # Verify ReAct trajectory
    trajectory = result["trajectory"]
    assert len(trajectory) >= 3
    phases = [step["phase"] for step in trajectory]
    assert "perception" in phases
    assert "diagnosis" in phases
    assert "synthesis" in phases

    # Verify strict hardware safety clamping <= 3.0 dB
    for step in result["proposal"]["steps"]:
        if step["action"] == "set_volume":
            assert abs(step["after"] - step["before"]) <= 0.20


def test_react_deliberate_offline_snapshot():
    agent = KennAutonomousAgent()
    result = agent.react_deliberate(
        "Balance the mix",
        session_id="offline-sess",
        session_snapshot={"status": "offline", "tracks": []},
    )

    assert result["ok"] is False
    assert result["status"] == "offline"
