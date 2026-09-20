"""Latency and size tests for LLM-powered agent tasks.

These benchmarks guard against model/prompt bloat for routine tasks.
No model training is started here; we only measure live Ollama latency
when available.
"""

from __future__ import annotations

import statistics
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = ROOT / "business" / "agents"

from Shared.agent_llm import _ollama_available
from Shared.agent_core import AgentCore


def _measure(func, *args, repeats: int = 3, **kwargs):
    timestamps = []
    for _ in range(repeats):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        timestamps.append(time.perf_counter() - start)
    return {
        "result": result,
        "avg": statistics.fmean(timestamps),
        "min": min(timestamps),
        "max": max(timestamps),
        "samples": timestamps,
    }


@pytest.mark.skipif(not _ollama_available(), reason="Ollama not available")
def test_fast_model_latency_for_small_tasks():
    agent = AgentCore(
        agent_name="Marketing",
        system_prompt_path=AGENTS_DIR / "Marketing" / "agent.md",
        tools=["marketing.new_lead", "shared.list_leads"],
    )
    stats = _measure(
        agent.generate,
        "Generate a one-sentence tagline for mixing services",
        command="outreach",
        max_tokens=120,
        fast=True,
        with_tools=False,
        repeats=3,
    )
    assert isinstance(stats["result"], str)
    assert len(stats["result"]) > 0
    assert stats["avg"] < 12.0, f"Latency too high: {stats['avg']:.2f}s"


@pytest.mark.skipif(not _ollama_available(), reason="Ollama not available")
def test_admin_task_latency_budget():
    agent = AgentCore(
        agent_name="Admin",
        system_prompt_path=AGENTS_DIR / "Admin" / "agent.md",
        tools=["admin.new_client", "admin.save_project"],
    )
    stats = _measure(
        agent.generate,
        "Draft a short follow-up email to client Jordan about mixing",
        command="email",
        max_tokens=180,
        fast=True,
        with_tools=False,
        repeats=3,
    )
    assert isinstance(stats["result"], str)
    assert len(stats["result"]) > 0
    assert stats["avg"] < 15.0, f"Latency too high: {stats['avg']:.2f}s"


@pytest.mark.skipif(not _ollama_available(), reason="Ollama not available")
def test_output_size_reasonably_bounded():
    agent = AgentCore(
        agent_name="Marketing",
        system_prompt_path=AGENTS_DIR / "Marketing" / "agent.md",
        tools=["marketing.new_lead", "shared.list_leads"],
    )
    stats = _measure(
        agent.generate,
        "Generate a concise team introduction for Audio_Too mixing services",
        command="outreach",
        max_tokens=140,
        fast=True,
        with_tools=False,
        repeats=2,
    )
    assert len(stats["result"]) < 1800, "Output is too large for a small task"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])