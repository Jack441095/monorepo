"""Environment-driven selection of KENN's Live backend."""

from __future__ import annotations

import os
from pathlib import Path
import shlex
from typing import Any, Callable, Mapping

from kenn.core.live_backend import CONTROL_DECK_READ_TOOLS, ControlDeckMCPBackend
from kenn.core.mcp_stdio import StdioMCPToolCaller


LIVE_BACKEND_ENV = "KENN_LIVE_BACKEND"
MCP_COMMAND_ENV = "KENN_LIVE_MCP_COMMAND"
MCP_CWD_ENV = "KENN_LIVE_MCP_CWD"
MCP_TIMEOUT_ENV = "KENN_LIVE_MCP_TIMEOUT_SECONDS"


def create_live_backend(
    osc_factory: Callable[[], Any],
    *,
    environ: Mapping[str, str] | None = None,
) -> Any:
    """Create the configured backend without silently crossing transports.

    ``osc`` remains the compatibility default.  Selecting
    ``control-deck-mcp`` requires an explicit stdio command; configuration
    errors fail during startup rather than falling back to OSC behind the
    operator's back.
    """

    values = os.environ if environ is None else environ
    selected = str(values.get(LIVE_BACKEND_ENV, "osc")).strip().casefold()
    if selected in {"osc", "abletonosc"}:
        return osc_factory()
    if selected == "fake":
        from kenn.core.fake_live import FakeLiveBackend

        return FakeLiveBackend()
    if selected not in {"mcp", "control-deck", "control-deck-mcp"}:
        raise RuntimeError(
            f"Unsupported {LIVE_BACKEND_ENV} value '{selected}'. "
            "Use 'osc', 'control-deck-mcp', or 'fake' (tests only)."
        )

    command_text = str(values.get(MCP_COMMAND_ENV, "")).strip()
    if not command_text:
        raise RuntimeError(
            f"{MCP_COMMAND_ENV} is required when {LIVE_BACKEND_ENV}=control-deck-mcp."
        )
    try:
        command = shlex.split(command_text)
    except ValueError as exc:
        raise RuntimeError(f"{MCP_COMMAND_ENV} is not a valid command: {exc}") from exc
    if not command:
        raise RuntimeError(f"{MCP_COMMAND_ENV} must contain an executable.")

    cwd_text = str(values.get(MCP_CWD_ENV, "")).strip()
    cwd = Path(cwd_text).expanduser() if cwd_text else None
    if cwd is not None and not cwd.is_dir():
        raise RuntimeError(f"{MCP_CWD_ENV} is not an existing directory: {cwd}")
    try:
        timeout_seconds = float(values.get(MCP_TIMEOUT_ENV, "8"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{MCP_TIMEOUT_ENV} must be a positive number.") from exc
    if timeout_seconds <= 0:
        raise RuntimeError(f"{MCP_TIMEOUT_ENV} must be a positive number.")

    caller = StdioMCPToolCaller(
        command,
        allowed_tools=CONTROL_DECK_READ_TOOLS,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
    )
    return ControlDeckMCPBackend(caller)


__all__ = [
    "LIVE_BACKEND_ENV",
    "MCP_COMMAND_ENV",
    "MCP_CWD_ENV",
    "MCP_TIMEOUT_ENV",
    "create_live_backend",
]
