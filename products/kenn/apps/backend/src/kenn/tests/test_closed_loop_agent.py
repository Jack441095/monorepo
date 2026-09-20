"""Tests for KENN Autonomous Grounded Closed-Loop Session Agent."""

import pytest
from kenn.autonomous_agent import KennAutonomousAgent
from kenn.core.action_policy import AutonomousSafetyEvaluator


def test_closed_loop_session_requires_autonomous_mode(monkeypatch):
    monkeypatch.setenv("KENN_AUTONOMOUS_MODE", "0")
    agent = KennAutonomousAgent()
    result = agent.execute_closed_loop_session("Balance sub and kick")
    assert result["ok"] is False
    assert "KENN_AUTONOMOUS_MODE=1" in result["error"]


def test_closed_loop_session_executes_with_world_model(monkeypatch):
    monkeypatch.setenv("KENN_AUTONOMOUS_MODE", "1")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")

    # Mock live_context_summary and LiveActionService
    import kenn.plugin_handoff as handoff
    monkeypatch.setattr(
        handoff,
        "live_context_summary",
        lambda _sid: {
            "peak_dbfs": -0.8,
            "rms_dbfs": -12.4,
            "crest_db": 11.6,
            "stereo_correlation": 0.85,
        },
    )

    from kenn.core.live_action_service import LiveActionService
    monkeypatch.setattr(
        LiveActionService,
        "snapshot",
        lambda _self: {
            "tracks": [
                {"index": 0, "name": "Kick", "volume": 0.85, "panning": 0.0, "devices": []},
                {"index": 1, "name": "Sub Bass", "volume": 0.80, "panning": 0.0, "devices": []},
            ],
            "scenes": [],
        },
    )

    agent = KennAutonomousAgent()
    result = agent.execute_closed_loop_session(
        acoustic_goal="Fix sub kick collision",
        session_id="test_session",
        max_iterations=1,
        stabilization_delay_seconds=0.0,
    )

    assert result["ok"] is True
    assert result["iterations_completed"] >= 1
    assert "world_model" in result
    assert result["world_model"]["total_tracks"] == 2
    assert "history" in result

