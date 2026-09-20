#!/usr/bin/env python3
"""Autonomous base class for all Audio_Too agents.

Any existing agent can inherit from AutonomousAgent to gain:
- Autonomous task execution via LLM planning
- Tool use (read/write files, run tests, lint)
- Self-healing retry loop
- Persistent memory
- Shared conversation memory for multi-agent collaboration
- Safety checks and permissions
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Ensure CodingAgent is importable
_CODING_AGENT_PATH = Path(__file__).parent.parent / "CodingAgent"
if str(_CODING_AGENT_PATH) not in sys.path:
    sys.path.insert(0, str(_CODING_AGENT_PATH))

from agent_loop import AutonomousCoderAgent
from memory import AgentMemory, ContextEnricher
from permissions import PermissionManager, SafetyChecks


class AutonomousAgent:
    """Base class that makes any agent autonomous with multi-agent collaboration support.

    Usage:
        class MyAgent(AutonomousAgent):
            def __init__(self):
                super().__init__(root=Path(__file__).parent.parent.parent)

            def my_custom_task(self):
                return self.run_task("Do something custom")
    """

    def __init__(
        self,
        root: Path | None = None,
        auto_approve: bool = False,
        model_plan: str | None = None,
        model_fast: str | None = None,
    ):
        self.root = (root or Path(".")).resolve()
        self.auto_approve = auto_approve
        self.agent_loop = AutonomousCoderAgent(
            root=self.root,
            auto_approve=auto_approve,
            model_plan=model_plan,
            model_fast=model_fast,
        )
        self.memory = AgentMemory(self.root)
        self.permissions = PermissionManager(self.root, auto_approve=auto_approve)
        self._shared = None

    @property
    def shared_memory(self):
        """Lazy-load shared memory for multi-agent collaboration."""
        if self._shared is None:
            from conversation_memory import get_shared_memory
            self._shared = get_shared_memory()
        return self._shared

    def run_task(self, task: str, max_retries: int = 3, handoff_context: str = "") -> dict[str, Any]:
        """Run an autonomous task with memory enrichment and shared context.

        Args:
            task: Natural language task description
            max_retries: Max fix attempts
            handoff_context: Context from another agent (for task handoffs)

        Returns:
            Result dict with success, plan, results, summary
        """
        # Add handoff context if provided
        enriched_task = handoff_context + " " + task if handoff_context else task
        enriched = ContextEnricher(self.memory).enrich_task_prompt(enriched_task)
        result = self.agent_loop.run(enriched, max_retries=max_retries)

        # Record in both local and shared memory
        try:
            from memory import AgentTurn
            self.memory.record_turn(
                AgentTurn(
                    task=task,
                    plan=result.get("plan", []),
                    results=result.get("results", []),
                    success=result.get("success", False),
                )
            )
            # Also add to shared memory for collaboration
            self.shared_memory.add_turn(
                agent=self.__class__.__name__,
                role="task",
                content=task,
                result={"success": result.get("success")},
            )
        except Exception:
            pass
        return result

    def handoff_to(self, other_agent_class: type, task: str) -> str:
        """Hand off a task to another agent.

        Returns:
            handoff_id for tracking the task
        """
        handoff_id = self.shared_memory.handoff_task(
            from_agent=self.__class__.__name__,
            to_agent=other_agent_class.__name__,
            task=task,
        )
        return handoff_id

    def get_handoffs(self) -> list[dict[str, Any]]:
        """Get pending handoffs for this agent."""
        all_handoffs = self.shared_memory.get_recent_tasks()
        return [h for h in all_handoffs if h.get("to") == self.__class__.__name__ and not h.get("completed")]

    def generate_code(self, task: str) -> str | None:
        """Delegate to CodingAgent for code generation."""
        return self.agent_loop._fallback_plan(task)

    def review_file(self, path: str) -> dict[str, Any]:
        """Review a file using the fast model."""
        return self.agent_loop._review_file(path)

    def is_safe_path(self, path: str) -> bool:
        return SafetyChecks.validate_path(self.root, path)[0]

    def get_memory_stats(self) -> dict[str, Any]:
        return self.memory.get_stats()

    def get_history(self, tail: int = 20):
        return self.memory.history[-tail:]

    def get_shared_conversations(self) -> dict[str, list[dict[str, Any]]]:
        """Get all conversations across all agents (for debugging/insight)."""
        return self.shared_memory.get_all_conversations()
