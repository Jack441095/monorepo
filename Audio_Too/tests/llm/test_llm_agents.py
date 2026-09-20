"""Tests for LLM-powered agents, memory, and tool use.

These tests cover the new Ollama-backed agent layer without requiring a live
model for the core logic tests. Tests that need generation are skipped if
Ollama is unavailable.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = ROOT / "business" / "agents"
sys.path.insert(0, str(AGENTS_DIR))

import pytest  # noqa: E402

from Shared.agent_memory import AgentMemory  # noqa: E402
from Shared.agent_router import route_request  # noqa: E402
from Shared.agent_tools import execute_tool, get_tool  # noqa: E402
from Shared.agent_llm import _ollama_available, generate_llm  # noqa: E402
from Shared.agent_core import AgentCore  # noqa: E402


# ── Memory tests ───────────────────────────────────────────────────────

class TestAgentMemory:
    def test_add_and_history(self):
        mem = AgentMemory(max_turns=3)
        mem.add("user", "Create a lead")
        mem.add("assistant", "Created lead")
        assert len(mem.as_chat_history()) == 2

    def test_max_turns(self):
        mem = AgentMemory(max_turns=2)
        for i in range(5):
            mem.add("user", f"Turn {i}")
        assert len(mem.as_chat_history()) == 4

    def test_recent_user_text(self):
        mem = AgentMemory()
        mem.add("user", "First")
        mem.add("assistant", "Resp")
        mem.add("user", "Second")
        assert mem.recent_user_text() == "Second"

    def test_clear(self):
        mem = AgentMemory()
        mem.add("user", "Hello")
        mem.clear()
        assert mem.as_chat_history() == []


# ── Router tests ───────────────────────────────────────────────────────

class TestAgentRouter:
    def test_marketing_action_beats_generic_admin_nouns(self):
        folder, args = route_request("Send a mastering offer to the new client")
        assert folder == "Marketing"
        assert args[0] == "offer"

    def test_social_routes_to_marketing(self):
        folder, args = route_request("Run a social media campaign")
        assert folder == "Marketing"

    def test_admin_routes_to_admin(self):
        folder, args = route_request("Draft an invoice for mastering")
        assert folder == "Admin"
        assert args[0] == "auto"


# ── Tool tests ─────────────────────────────────────────────────────────

class TestAgentTools:
    def test_get_tool_exists(self):
        assert get_tool("marketing.new_lead") is not None
        assert get_tool("admin.new_client") is not None

    def test_get_tool_missing(self):
        assert get_tool("missing.tool") is None

    def test_execute_tool_list_leads(self):
        result = execute_tool("shared.list_leads", AGENTS_DIR)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_execute_tool_list_projects(self):
        result = execute_tool("shared.list_projects", AGENTS_DIR)
        assert isinstance(result, str)
        assert len(result) > 0


# ── LLM connectivity tests ─────────────────────────────────────────────

class TestLLM:
    def test_ollama_available(self):
        # Should not raise; may be True/False depending on environment
        _ollama_available()

    @pytest.mark.skipif(not _ollama_available(), reason="Ollama not available")
    def test_llm_generation(self):
        text = generate_llm(
            system_prompt="You are a test assistant. Reply with the single word OK.",
            user_prompt="Reply OK",
            max_tokens=20,
            fast=True,
        )
        assert text and "OK" in text


# ── AgentCore tests ────────────────────────────────────────────────────

class TestAgentCore:
    def test_marketing_agent_has_tools(self):
        agent = AgentCore(
            agent_name="Marketing",
            system_prompt_path=AGENTS_DIR / "Marketing" / "agent.md",
            tools=["marketing.new_lead", "shared.list_leads"],
        )
        tool_names = [t.name for t in agent.tools]
        assert "marketing.new_lead" in tool_names

    def test_admin_agent_has_tools(self):
        agent = AgentCore(
            agent_name="Admin",
            system_prompt_path=AGENTS_DIR / "Admin" / "agent.md",
            tools=["admin.new_client", "admin.save_project", "shared.list_projects"],
        )
        tool_names = [t.name for t in agent.tools]
        assert "admin.new_client" in tool_names

    @pytest.mark.skipif(_ollama_available(), reason="Requires Ollama to be unavailable")
    def test_fallback_when_llm_unavailable(self):
        agent = AgentCore(
            agent_name="Test",
            system_prompt_path=AGENTS_DIR / "Marketing" / "agent.md",
            fallback_generator=lambda cmd, task: "fallback",
            tools=[],
        )
        result = agent.generate("test task", with_tools=False)
        assert "fallback" in result.lower()

    @pytest.mark.skipif(not _ollama_available(), reason="Ollama not available")
    def test_marketing_generation(self):
        agent = AgentCore(
            agent_name="Marketing",
            system_prompt_path=AGENTS_DIR / "Marketing" / "agent.md",
            tools=["marketing.new_lead", "shared.list_leads"],
        )
        result = agent.generate(
            task="Generate a one-sentence tagline for mixing services",
            command="outreach",
            max_tokens=120,
            fast=True,
            with_tools=False,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.skipif(not _ollama_available(), reason="Ollama not available")
    def test_admin_generation(self):
        agent = AgentCore(
            agent_name="Admin",
            system_prompt_path=AGENTS_DIR / "Admin" / "agent.md",
            tools=["admin.new_client", "admin.save_project"],
        )
        result = agent.generate(
            task="Draft a short follow-up email to client Jordan about their mixing project",
            command="email",
            max_tokens=180,
            fast=True,
            with_tools=False,
        )
        assert isinstance(result, str)
        assert len(result) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])