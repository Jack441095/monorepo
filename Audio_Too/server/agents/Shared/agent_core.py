#!/usr/bin/env python3
"""Base agent class powered by local LLM.

Each agent (Marketing, Admin, etc.) creates an AgentCore with:
- system_prompt: loaded from their agent.md file
- agent_name: for logging/identification
- memory: short-term conversation memory
- tools: optional function-calling tools the agent can invoke autonomously
- fallback_templates: simple text generation if LLM is unavailable

The core handles:
1. Try LLM generation with the system prompt
2. Extract structured fields from LLM output
3. Fall back to simple templates if LLM is down
4. Multi-turn memory across requests
5. Tool calling when the LLM decides an action is needed
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from Shared.agent_llm import generate_llm, extract_structured_field, extract_structured_fields
from Shared.agent_memory import AgentMemory
from Shared.agent_tools import get_tool, execute_tool


class AgentCore:
    """Base class for LLM-powered agents with memory and tool use.

    Usage:
        agent = AgentCore(
            agent_name="Marketing",
            system_prompt_path=Path("Marketing/agent.md"),
            tools=["marketing.new_lead", "shared.list_leads"],
        )
        response = agent.chat("Create a lead for The Echoes")
        response = agent.chat("Now draft outreach to them")
    """

    def __init__(
        self,
        agent_name: str,
        system_prompt_path: Path,
        fallback_generator: Callable[[str, str], str] | None = None,
        model: str | None = None,
        fast_model: str | None = None,
        tools: list[str] | None = None,
        max_turns: int = 6,
    ):
        self.agent_name = agent_name
        self.system_prompt_path = system_prompt_path
        self._system_prompt: str | None = None
        self._fallback_generator = fallback_generator
        self.model = model
        self.fast_model = fast_model
        self.memory = AgentMemory(max_turns=max_turns)
        self.tools = [get_tool(name) for name in (tools or []) if get_tool(name)]

    @property
    def system_prompt(self) -> str:
        """Lazy-load system prompt from agent.md file."""
        if self._system_prompt is None:
            if self.system_prompt_path.exists():
                self._system_prompt = self.system_prompt_path.read_text(encoding="utf-8").strip()
            else:
                self._system_prompt = f"You are the {self.agent_name} agent for Audio_Too."
        return self._system_prompt

    def _build_tool_prompt(self) -> str:
        if not self.tools:
            return ""
        lines = ["Available tools:"]
        for tool in self.tools:
            lines.append(f"- {tool.name}: {tool.description}")
            if tool.schema:
                params = ", ".join(f"{k}={v}" for k, v in tool.schema.items())
                lines.append(f"  Params: {params}")
        instructions = (
            "\nIf you need to act, respond with a tool call on its own line in this exact format:\n"
            "TOOL: <tool.name> <param>=<value> <param>=<value>\n"
            "Otherwise, just answer normally.\n"
        )
        return "\n".join(lines) + instructions

    def _handle_tool_call(self, text: str, root: Any) -> tuple[str, bool]:
        match = re.search(r"^(?:TOOL:\s*)?(\S+)(?::\s*)(\S.*)?$", text, re.M)
        if not match:
            return text, False
        tool_name = match.group(1).strip()
        args_str = (match.group(2) or "").strip()
        tool = get_tool(tool_name)
        if not tool:
            return f"I couldn't find tool '{tool_name}'.", True
        kwargs: dict[str, str] = {}
        for m in re.finditer(r"(\w+)=([^ ]+)", args_str):
            kwargs[m.group(1)] = m.group(2)
        try:
            result = execute_tool(tool_name, root, **kwargs)
        except TypeError as exc:
            return f"Tool call failed: {exc}", True
        return f"Tool result: {result}", True

    def generate(
        self,
        task: str,
        *,
        command: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 600,
        fast: bool = False,
        with_tools: bool = True,
    ) -> str:
        """Generate a response using LLM, with optional tool calling."""
        self.memory.add("user", task)
        tool_prompt = self._build_tool_prompt() if with_tools and self.tools else ""
        context = self.memory.as_prompt_context()
        user_prompt = "\n".join(part for part in [context, f"Command: {command}" if command else None, f"Task: {task}", tool_prompt] if part)

        llm_output = generate_llm(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            fast=fast,
        )

        if not llm_output:
            if self._fallback_generator:
                fb = self._fallback_generator(command or "auto", task)
                self.memory.add("assistant", fb)
                return fb
            fb = f"[{self.agent_name}] No response generated."
            self.memory.add("assistant", fb)
            return fb

        if "TOOL:" in llm_output and self.tools:
            result_text, handled = self._handle_tool_call(llm_output, Path.cwd())
            if handled:
                follow_up_prompt = (
                    f"{context}\nTask: {task}\nTool result:\n{result_text}\n\n"
                    "Use this result to complete the user's request."
                )
                llm_output = generate_llm(
                    system_prompt=self.system_prompt,
                    user_prompt=follow_up_prompt,
                    model=self.model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    fast=fast,
                ) or result_text

        self.memory.add("assistant", llm_output)
        return llm_output

    def generate_with_format(
        self,
        task: str,
        *,
        command: str | None = None,
        format_instructions: str = "",
        temperature: float = 0.3,
        max_tokens: int = 600,
        fast: bool = False,
        with_tools: bool = False,
    ) -> str:
        """Generate with explicit format requirements in the prompt."""
        self.memory.add("user", task)
        parts = []
        context = self.memory.as_prompt_context()
        if context:
            parts.append(context)
        if command:
            parts.append(f"Command: {command}")
        parts.append(f"Task: {task}")
        if format_instructions:
            parts.append(format_instructions)
        user_prompt = "\n".join(parts)

        llm_output = generate_llm(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            fast=fast,
        )

        if not llm_output:
            if self._fallback_generator:
                fb = self._fallback_generator(command or "auto", task)
                self.memory.add("assistant", fb)
                return fb
            fb = f"[{self.agent_name}] No response generated."
            self.memory.add("assistant", fb)
            return fb

        if with_tools and self.tools and "TOOL:" in llm_output:
            result_text, handled = self._handle_tool_call(llm_output, Path.cwd())
            if handled:
                follow_up_prompt = (
                    f"{context}\nTask: {task}\nTool result:\n{result_text}\n\n"
                    "Use this result to complete the user's request."
                )
                llm_output = generate_llm(
                    system_prompt=self.system_prompt,
                    user_prompt=follow_up_prompt,
                    model=self.model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    fast=fast,
                ) or result_text

        self.memory.add("assistant", llm_output)
        return llm_output

    def extract_field(self, text: str, field: str) -> str | None:
        return extract_structured_field(text, field)

    def extract_fields(self, text: str, fields: list[str]) -> dict[str, str]:
        return extract_structured_fields(text, fields)

    def quick_response(self, task: str, max_tokens: int = 200) -> str:
        return self.generate(
            task=task,
            temperature=0.2,
            max_tokens=max_tokens,
            fast=True,
        )

    def chat(self, task: str, **kwargs) -> str:
        """Multi-turn chat helper; retains memory across calls."""
        return self.generate(task=task, **kwargs)

    def reset_memory(self) -> None:
        self.memory.clear()