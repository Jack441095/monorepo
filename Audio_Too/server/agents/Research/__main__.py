#!/usr/bin/env python3
"""CLI entrypoint for autonomous Research agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_AGENT_DIR = Path(__file__).parent
_SYSTEM_ROOT = _AGENT_DIR.parent.parent.parent
sys.path.insert(0, str(_SYSTEM_ROOT / "business" / "agents" / "CodingAgent"))
sys.path.insert(0, str(_SYSTEM_ROOT / "business" / "agents" / "Shared"))

from agent_loop import ResearchAgent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-agent",
        description="Autonomous Research agent for Audio_Too",
    )
    parser.add_argument("--root", type=Path, default=_SYSTEM_ROOT)
    parser.add_argument("--dangerous", action="store_true")
    parser.add_argument("--json", action="store_true")

    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="Run task")
    p_run.add_argument("task")

    p_topic = sub.add_parser("topic", help="Research topic")
    p_topic.add_argument("topic")
    p_topic.add_argument("--depth", default="standard")

    p_trends = sub.add_parser("trends", help="Analyze trends")
    p_trends.add_argument("domain")

    p_report = sub.add_parser("report", help="Compile report")
    p_report.add_argument("subject")

    p_bench = sub.add_parser("benchmark", help="Benchmark competitors")
    p_bench.add_argument("competitors", nargs="+")

    sub.add_parser("memory", help="Memory stats")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0

    agent = ResearchAgent(root=args.root, auto_approve=args.dangerous)
    result = None

    if args.command == "run":
        result = agent.run_task(args.task)
    elif args.command == "topic":
        result = agent.research_topic(args.topic, args.depth)
    elif args.command == "trends":
        result = agent.analyze_trends(args.domain)
    elif args.command == "report":
        result = agent.compile_report(args.subject)
    elif args.command == "benchmark":
        result = agent.benchmark_competitors(args.competitors)
    elif args.command == "memory":
        print(json.dumps(agent.get_memory_stats(), indent=2))
        return 0

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Task: {args.command}")
        print(f"Success: {result.get('success')}")
        print(f"Summary: {result.get('summary')}")
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
