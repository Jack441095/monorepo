#!/usr/bin/env python3
"""Backward-compatible Research agent interface."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load ResearchAgent from local agent_loop.py
_AGENT_DIR = Path(__file__).parent
_AGENT_LOOP_PATH = _AGENT_DIR / "agent_loop.py"
_spec = importlib.util.spec_from_file_location("research_agent_loop", _AGENT_LOOP_PATH)
_agent_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_agent_module)
ResearchAgent = _agent_module.ResearchAgent


def research_topic(topic: str, depth: str = "standard", auto_approve: bool = False):
    return ResearchAgent(auto_approve=auto_approve).research_topic(topic, depth)


def analyze_trends(domain: str, auto_approve: bool = False):
    return ResearchAgent(auto_approve=auto_approve).analyze_trends(domain)


def compile_report(subject: str, auto_approve: bool = False):
    return ResearchAgent(auto_approve=auto_approve).compile_report(subject)


def benchmark_competitors(competitors: list[str], auto_approve: bool = False):
    return ResearchAgent(auto_approve=auto_approve).benchmark_competitors(competitors)


if __name__ == "__main__":
    # This file is a library-only "backward-compatible interface" (see the
    # module docstring), but business/agents/agent's legacy subprocess
    # dispatch path still invokes it as `python3 Research/main.py <sub_command>
    # <fields...>` (thursday/client.py::_run_agent) -- with no __main__ guard,
    # that ran this file top-to-bottom (defining functions and exiting) and
    # silently produced zero output for every command. Identical bug, fixed
    # the same way, as Admin/main.py's own __main__ guard (see that file's
    # comment for the incident writeup), and the same fix just applied to
    # Marketing/main.py. This file already defines its own correctly-shaped
    # convenience functions above, so this dispatches directly to them.
    #
    # auto_approve stays False (the default) -- see Marketing/main.py's
    # matching block for the full writeup. Short version: an earlier version
    # passed True on the reasoning that Thursday's confirmation gate had
    # already vetted the request; a 2026-09-08 security review found that
    # wrong (research/drafting requests classify as PROPOSAL, which requires
    # no confirmation). Not exploitable, since these commands route to
    # _generate_content()/generate_llm() and never consult the flag -- but
    # False costs nothing and removes a latent privilege-escalation footgun.
    import json as _json

    _args = sys.argv[1:]
    _command = _args[0] if _args else None
    _fields = _args[1:]

    _result = None
    if _command == "topic" and len(_fields) >= 1:
        _result = research_topic(_fields[0])
    elif _command == "trends" and len(_fields) >= 1:
        _result = analyze_trends(_fields[0])
    elif _command == "report" and len(_fields) >= 1:
        _result = compile_report(_fields[0])
    elif _command == "benchmark" and len(_fields) >= 1:
        _result = benchmark_competitors(_fields)
    else:
        print(f"Unknown research command or missing arguments: {_args!r}", file=sys.stderr)
        raise SystemExit(2)

    print(_json.dumps(_result))
    raise SystemExit(0 if _result.get("success") else 1)