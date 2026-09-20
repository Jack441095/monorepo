"""nite — minimal local runtime client CLI (engineering tool, not final UX).

Usage:
    python -m nite_ai.cli --socket /path/to/runtime.sock handshake
    python -m nite_ai.cli --socket ... --json brief
"""

from __future__ import annotations

import argparse
import json
import socket
import sys

from nite_ai import __version__
from nite_ai.runtime import PROTOCOL_VERSION, RuntimeClient, RuntimeUnavailable

_COMMAND_TO_CAPABILITY = {
    "brief": "company.brief.daily",
    "review": "company.review.weekly",
    "goals": "company.goals.list",
    "tasks": "company.tasks.list",
    "agents": "company.agents.status",
    "approvals": "company.approvals.pending",
    "risks": "company.risks.list",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nite")
    parser.add_argument("--socket", required=True, help="runtime unix socket path")
    parser.add_argument("--json", action="store_true", help="raw JSON output")
    parser.add_argument("command", help="handshake | " + " | ".join(sorted(_COMMAND_TO_CAPABILITY)))
    args = parser.parse_args(argv)

    client = RuntimeClient(args.socket)
    try:
        if args.command == "handshake":
            response = client.call({"protocol_version": PROTOCOL_VERSION,
                                    "request_id": "cli-handshake",
                                    "operation": "handshake"})
        else:
            capability = _COMMAND_TO_CAPABILITY.get(args.command)
            if capability is None:
                print(f"unknown command: {args.command}", file=sys.stderr)
                return 2
            response = client.call({
                "protocol_version": PROTOCOL_VERSION,
                "request_id": f"cli-{args.command}",
                "operation": capability,
                "payload": {"granted_permissions": ["read"]},
                "trace": {"trace_id": f"cli-{args.command}"},
            })
    except RuntimeUnavailable as exc:
        print(f"runtime unavailable at {args.socket}: {exc}", file=sys.stderr)
        return 3
    except socket.timeout:
        print("runtime timed out", file=sys.stderr)
        return 4
    except OSError as exc:
        print(f"protocol/runtime error: {exc}", file=sys.stderr)
        return 5

    if args.json:
        print(json.dumps(response, indent=2, sort_keys=True))
        return 0 if response.get("status") == "success" else 1

    if response.get("status") != "success":
        err = response.get("error") or {}
        print(f"error [{err.get('code')}]: {err.get('message')}", file=sys.stderr)
        return 1
    payload = response.get("payload") or {}
    if "daily_brief" in payload:
        b = payload["daily_brief"]
        print(f"Daily brief — {b['brief_date']}")
        print(f"  priorities: {', '.join(b['top_priorities']) or 'none'}")
        print(f"  blockers:   {', '.join(b['blockers']) or 'none'}")
        print(f"  goals at risk: {', '.join(b['goals_at_risk']) or 'none'}")
    elif response.get("status") == "success" and args.command == "handshake":
        print(f"runtime ok — platform {payload.get('platform_version')}, "
              f"protocol {payload.get('protocol_version')}")
        for cap in payload.get("capabilities", []):
            print(f"  - {cap}")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
