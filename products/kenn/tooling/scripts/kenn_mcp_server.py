#!/usr/bin/env python3
"""Run KENN's guarded Ableton MCP facade over stdio.

Example:
    PYTHONPATH=apps/backend/src python3 tooling/scripts/kenn_mcp_server.py

The process speaks newline-delimited JSON-RPC on stdout and keeps diagnostics
off stdout so MCP clients can consume the stream safely. It talks only to the
running local KENN companion at ``127.0.0.1:8090``; all Live writes still go
through KENN's exact proposal, confirmation, stale-state, readback, replay,
and undo boundary.
"""

from __future__ import annotations

import json
import os
import sys

from kenn.core.mcp_facade import KennHTTPClient, KennMCPFacade
from kenn.core.ollama_deliberative import OllamaDeliberativeGenerator


_DISABLED_MODEL_VALUES = {"", "0", "off", "false", "disabled"}
_PLANNER_PROVIDERS = {"ollama", "transformers"}


def planner_identity(environment: dict[str, str] | os._Environ[str] = os.environ) -> tuple[str, str]:
    """Return an explicit model/provider identity; fresh installs fail closed."""
    model = str(environment.get("KENN_DELIBERATIVE_MODEL", "off")).strip()
    if model.casefold() in _DISABLED_MODEL_VALUES:
        return "disabled", "disabled"
    provider = str(environment.get("KENN_DELIBERATIVE_PROVIDER", "ollama")).strip().casefold()
    if provider not in _PLANNER_PROVIDERS:
        raise ValueError("KENN_DELIBERATIVE_PROVIDER must be 'ollama' or 'transformers'.")
    return model[:128], provider


def main() -> int:
    base_url = os.getenv("KENN_MCP_COMPANION_URL", "http://127.0.0.1:8090")
    # AudioGen symbolic MIDI generation is intentionally slow compared with a
    # Live read. Keep the stdio facade patient for proposal-only generation;
    # Live apply/undo still use the same guarded HTTP boundary.
    timeout = float(os.getenv("KENN_MCP_TIMEOUT", "120"))
    planner_model, planner_provider = planner_identity()
    planner = None
    if planner_model != "disabled":
        planner = OllamaDeliberativeGenerator(
            model=planner_model,
            base_url=os.getenv("KENN_DELIBERATIVE_OLLAMA_URL", "http://127.0.0.1:11434"),
            timeout=float(os.getenv("KENN_DELIBERATIVE_TIMEOUT", "45")),
            max_output_tokens=int(os.getenv("KENN_DELIBERATIVE_MAX_TOKENS", "320")),
        )
    facade = KennMCPFacade(
        KennHTTPClient(base_url=base_url, timeout=timeout),
        planner=planner,
        planner_provider=planner_provider,
        planner_id=planner_model if planner is not None else "disabled",
    )
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            response = facade.handle_message(message)
            if response is not None:
                sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
