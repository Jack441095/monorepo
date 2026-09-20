#!/usr/bin/env python3
"""Autonomous agent loop for Research agent."""

from __future__ import annotations

import sys
from pathlib import Path

_AGENT_DIR = Path(__file__).parent
_SYSTEM_ROOT = _AGENT_DIR.parent.parent.parent
sys.path.insert(0, str(_SYSTEM_ROOT / "business" / "agents" / "CodingAgent"))
sys.path.insert(0, str(_SYSTEM_ROOT / "business" / "agents" / "Shared"))

from autonomous_base import AutonomousAgent
from agent_llm import generate_llm


class ResearchAgent(AutonomousAgent):
    """Autonomous Research agent."""

    def __init__(self, root: Path | None = None, auto_approve: bool = False):
        super().__init__(
            root=root or _SYSTEM_ROOT,
            auto_approve=auto_approve,
        )

    def _generate_content(self, system_prompt: str, user_prompt: str) -> dict:
        """Direct LLM text completion -- deliberately bypasses
        self.run_task()'s AutonomousCoderAgent planning loop (code-editing
        tools only: write_file, run_tests, lint, git, search), which
        produced nonsensical results for content/analysis tasks in
        practice -- see Marketing/agent_loop.py's identical fix for the
        incident this was found in. Uses Shared/agent_llm.py's
        generate_llm() (a local Ollama call, no audio_too package
        dependency) rather than self.agent_loop/run_task.
        """
        # 300, not 500: found live that this genuinely timed out (60s+,
        # agent_llm.py's hardcoded TIMEOUT) at 500 tokens with the local 7B
        # model on this hardware -- see Marketing/agent_loop.py's identical
        # note. Errors there are swallowed to a plain None, indistinguishable
        # from "the model is unavailable," so staying comfortably under the
        # ceiling matters more here than a longer answer.
        content = generate_llm(system_prompt, user_prompt, temperature=0.4, max_tokens=300)
        if not content:
            return {"success": False, "summary": "LLM generation failed or Ollama unavailable."}
        return {"success": True, "summary": content, "content": content}

    # Shorter, terser system prompts than first tried: found live that
    # prompt length itself (prefill time), not just max_tokens, meaningfully
    # affects whether a call finishes inside agent_llm.py's 60s timeout on
    # this hardware -- see _generate_content's note. Each still keeps the
    # essential "no live web access, don't invent specifics" guardrail.

    def research_topic(self, topic: str, depth: str = "standard") -> dict:
        return self._generate_content(
            system_prompt=(
                "Research assistant, no live web access. Be concise (3-5 sentences). "
                "Never invent statistics, names, or dates you can't verify -- say so "
                "instead of guessing."
            ),
            user_prompt=f"Research topic ({depth} depth): {topic}",
        )

    def analyze_trends(self, domain: str) -> dict:
        return self._generate_content(
            system_prompt=(
                "Research assistant, no live web access. Be concise (3-5 sentences). "
                "Describe only general, well-known structural trends -- never invent "
                "recent statistics or dates."
            ),
            user_prompt=f"Trends in: {domain}",
        )

    def compile_report(self, subject: str) -> dict:
        return self._generate_content(
            system_prompt=(
                "Research assistant, no live web access. Be concise (3-5 sentences). "
                "Never invent citations or figures -- write '[needs verification]' "
                "where you're not certain."
            ),
            user_prompt=f"Report subject: {subject}",
        )

    def benchmark_competitors(self, competitors: list[str]) -> dict:
        return self._generate_content(
            system_prompt=(
                "Research assistant, no live web access or real data feed for named "
                "companies. Be concise (3-5 sentences). Never invent pricing, "
                "features, or market share -- flag that a real benchmark needs live data."
            ),
            user_prompt=f"Competitors: {', '.join(competitors)}",
        )