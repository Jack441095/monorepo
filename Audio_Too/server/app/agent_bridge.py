"""Run Admin/Marketing agents from the dashboard API."""

from __future__ import annotations

import sys
from pathlib import Path

AGENTS_ROOT = Path(__file__).resolve().parent.parent / "agents"
if str(AGENTS_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENTS_ROOT))

from Shared.agent_router import run_agent_task as _run_agent_task  # noqa: E402


def run_agent_task(task: str, *, agent: str = "auto") -> dict:
    return _run_agent_task(task, agent=agent, source="dashboard")
