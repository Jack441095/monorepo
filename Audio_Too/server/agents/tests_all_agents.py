#!/usr/bin/env python3
"""Tests for surviving agents."""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT / "server" / "agents" / "Shared"))


@pytest.fixture
def root():
    return _ROOT


class TestResearchAgent:
    def test_has_agent_loop(self, root):
        from server.agents.Research.agent_loop import ResearchAgent
        agent = ResearchAgent(root=root)
        assert hasattr(agent, "run_task")
        assert hasattr(agent, "research_topic")

    def test_backward_compat(self, root):
        from server.agents.Research.main import research_topic
        assert callable(research_topic)


class TestSharedBase:
    def test_autonomous_base_exists(self, root):
        shared_path = Path(__file__).parent.parent / "Shared"
        if str(shared_path) not in sys.path:
            sys.path.insert(0, str(shared_path))
        from autonomous_base import AutonomousAgent
        assert hasattr(AutonomousAgent, "run_task")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
