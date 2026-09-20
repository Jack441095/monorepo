#!/usr/bin/env python3
"""Conversation memory for agent multi-turn interactions.

Each agent can maintain a meaningful short-term memory across turns so it
remembers earlier requests and results. This is intentionally small to keep
token usage low and latency down.
"""

from __future__ import annotations



class AgentMemory:
    """Short-term memory for an agent conversation.

    Usage:
        memory = AgentMemory(max_turns=6)
        memory.add("user", "Create a lead for The Echoes")
        memory.add("assistant", "Created lead: The Echoes / Mixing")
        memory.add("user", "Now draft outreach to them")
        context = memory.as_prompt_context()
    """

    def __init__(self, max_turns: int = 6):
        self.max_turns = max_turns
        self._turns: list[dict[str, str]] = []

    def add(self, role: str, content: str) -> None:
        self._turns.append({"role": role, "content": content})
        if len(self._turns) > self.max_turns * 2:
            self._turns = self._turns[-self.max_turns * 2 :]

    def as_chat_history(self) -> list[dict[str, str]]:
        return list(self._turns)

    def as_prompt_context(self) -> str:
        if not self._turns:
            return ""
        lines = ["Conversation so far:"]
        for turn in self._turns:
            lines.append(f"- {turn['role'].title()}: {turn['content']}")
        return "\n".join(lines)

    def recent_user_text(self) -> str:
        for turn in reversed(self._turns):
            if turn["role"] == "user":
                return turn["content"]
        return ""

    def clear(self) -> None:
        self._turns = []