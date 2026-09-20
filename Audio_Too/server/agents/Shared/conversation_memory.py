#!/usr/bin/env python3
"""Shared conversation memory for multi-agent collaboration.

All agents can read/write to a shared memory to enable collaboration.
This provides:
- Global conversation history across all agents
- Task handoff between agents
- Shared context for multi-step workflows
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


class SharedMemory:
    """A singleton conversation memory shared across all agents."""

    _instance: SharedMemory | None = None
    _initialized: bool = False

    def __new__(cls) -> SharedMemory:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if SharedMemory._initialized:
            return
        SharedMemory._initialized = True

        # Memory file in project root
        self.memory_file = Path(os.getcwd()) / ".agent_shared_memory.json"
        self._conversations: dict[str, list[dict[str, Any]]] = {}
        self._tasks: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load shared memory from disk."""
        if not self.memory_file.exists():
            return
        try:
            data = json.loads(self.memory_file.read_text())
            self._conversations = data.get("conversations", {})
            self._tasks = data.get("tasks", {})
        except Exception:
            pass

    def _save(self) -> None:
        """Persist memory to disk."""
        try:
            data = {
                "conversations": self._conversations,
                "tasks": self._tasks,
                "updated": datetime.now().isoformat(),
            }
            self.memory_file.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def add_turn(self, agent: str, role: str, content: str, result: dict | None = None) -> None:
        """Add a conversation turn for an agent."""
        if agent not in self._conversations:
            self._conversations[agent] = []

        self._conversations[agent].append(
            {
                "role": role,
                "content": content,
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
        )
        # Trim to last 50 turns per agent
        self._conversations[agent] = self._conversations[agent][-50:]
        self._save()

    def get_conversation(self, agent: str, last_n: int = 10) -> list[dict[str, Any]]:
        """Get recent conversation history for an agent."""
        return self._conversations.get(agent, [])[-last_n:]

    def get_all_conversations(self) -> dict[str, list[dict[str, Any]]]:
        """Get all conversations across all agents."""
        return self._conversations

    def share_context(self, task_id: str, context: str, from_agent: str) -> None:
        """Share context for a task with other agents."""
        self._tasks[task_id] = {
            "context": context,
            "from_agent": from_agent,
            "timestamp": datetime.now().isoformat(),
        }
        self._save()

    def get_shared_context(self, task_id: str) -> str | None:
        """Get shared context for a task."""
        task = self._tasks.get(task_id)
        return task.get("context") if task else None

    def handoff_task(self, from_agent: str, to_agent: str, task: str, context: str = "") -> str:
        """Hand off a task from one agent to another. Returns handoff_id."""
        handoff_id = f"handoff_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._tasks[handoff_id] = {
            "type": "handoff",
            "from": from_agent,
            "to": to_agent,
            "task": task,
            "context": context,
            "timestamp": datetime.now().isoformat(),
            "completed": False,
        }
        self._save()
        return handoff_id

    def get_handoff(self, handoff_id: str) -> dict[str, Any] | None:
        """Get handoff details."""
        task = self._tasks.get(handoff_id)
        if task and task.get("type") == "handoff":
            return task
        return None

    def complete_handoff(self, handoff_id: str, result: dict | None = None) -> None:
        """Mark a handoff as complete."""
        if handoff_id in self._tasks:
            self._tasks[handoff_id]["completed"] = True
            self._tasks[handoff_id]["result"] = result
            self._save()

    def get_recent_tasks(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent tasks across all agents."""
        tasks = [
            {"id": k, **v}
            for k, v in self._tasks.items()
            if v.get("type") == "handoff"
        ]
        tasks.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return tasks[:limit]


# Global accessor
_shared_memory: SharedMemory | None = None


def get_shared_memory() -> SharedMemory:
    """Get the singleton shared memory instance."""
    global _shared_memory
    if _shared_memory is None:
        _shared_memory = SharedMemory()
    return _shared_memory