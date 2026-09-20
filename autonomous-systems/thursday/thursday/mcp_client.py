"""Generic MCP (Model Context Protocol) client capability for Thursday.

Disabled by default -- no specific external marketing platform (social
scheduler, ad platform, email tool) has been chosen yet as of 2026-09-07.
This module exists so Thursday can connect to a real MCP server once one is
picked, without new architecture: it reuses the existing confirmation
pattern (thursday.confirmation) rather than inventing a parallel one, the
same way every other external action in this codebase is gated.

Every tool call is treated as the most conservative risk classification
available (registry.core.ActionRisk.EXTERNAL_COMMUNICATION) unconditionally
-- a generic MCP server's tool semantics can't be known in advance, so no
per-tool trust list exists. call_tool() requires an already-issued, valid
confirmation token bound to the exact tool name + arguments; it never
executes on its own say-so, regardless of what the tool claims to do.

Env vars (both optional; unset = disabled, not silently no-op -- list_tools()
and call_tool() raise MCPUnavailable with a clear message):
  THURSDAY_MCP_SERVER_COMMAND  shell command to launch a stdio-based MCP
                                server (e.g. "npx @some/mcp-server"),
                                space-separated.
  THURSDAY_MCP_SERVER_URL      URL of a Streamable HTTP MCP server.

Requires the official `mcp` Python SDK (lazy-imported inside _transport() --
not a hard dependency, same pattern as audio_too/nite_ai elsewhere in this
codebase). VERIFIED 2026-09-07 against a real local install (mcp==2.2.0)
and a real, self-hosted stdio test server (mcp.server.mcpserver.MCPServer)
-- not just read against documentation. The v2 SDK's `mcp.Client` unifies
stdio and Streamable HTTP transports behind one constructor (a
StdioServerParameters instance, or a plain URL string); the old v1-era
`ClientSession`/`stdio_client`/`sse_client` composition this module
originally used is legacy and was replaced after finding it didn't match
what `pip install mcp` actually installs today (SSE in particular is not
part of the v2 top-level API surface at all). Real end-to-end call
(list_tools + call_tool against a live subprocess server) confirmed the
exact shapes used below: Tool.name/.description, and CallToolResult's
.content (list of content blocks)/.structured_content (dict)/.is_error.
NOT yet verified against a Streamable HTTP server (only stdio was
available to test locally) -- verify THURSDAY_MCP_SERVER_URL against a
real HTTP server before relying on it.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from dataclasses import dataclass
from typing import Any

from thursday.confirmation import verify_confirmation


class MCPUnavailable(RuntimeError):
    """Raised when the mcp SDK isn't installed, or no server is configured."""


class MCPConfirmationRequired(RuntimeError):
    """Raised when call_tool() is invoked without a valid, matching confirmation token."""


@dataclass
class MCPToolInfo:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class MCPCallResult:
    text: str               # concatenated text content blocks, for simple callers
    structured_content: Any  # the tool's raw structured_content, if any
    is_error: bool


def _server_command() -> list[str] | None:
    configured = os.environ.get("THURSDAY_MCP_SERVER_COMMAND", "").strip()
    return shlex.split(configured) if configured else None


def _server_url() -> str | None:
    return os.environ.get("THURSDAY_MCP_SERVER_URL", "").strip() or None


def is_configured() -> bool:
    """True if either env var names a server. Does not verify the server
    is actually reachable -- see health_check() for that."""
    return bool(_server_command() or _server_url())


class MCPToolProvider:
    """Thin synchronous wrapper over the async `mcp` v2 SDK's high-level
    `Client`, matching the synchronous style of the rest of Thursday's
    integration layer (thursday.llm_provider, thursday.client)."""

    def _require_configured(self) -> None:
        if not is_configured():
            raise MCPUnavailable(
                "No MCP server configured -- set THURSDAY_MCP_SERVER_COMMAND or "
                "THURSDAY_MCP_SERVER_URL. No specific platform is wired up as of "
                "2026-09-07; see docs/THURSDAY_SPECIALIST_PERMISSION_MATRIX_V1.md."
            )

    def _server_target(self):
        """Return the single argument mcp.Client's constructor takes --
        either a StdioServerParameters instance or a plain URL string; the
        v2 SDK's Client dispatches on the type of this one argument."""
        try:
            from mcp import StdioServerParameters
        except ImportError as exc:
            raise MCPUnavailable(f"mcp SDK not installed: {exc}") from exc

        command = _server_command()
        if command:
            return StdioServerParameters(command=command[0], args=command[1:])
        url = _server_url()
        if url:
            return url
        raise MCPUnavailable("No MCP server configured")

    async def _list_tools_async(self) -> list[MCPToolInfo]:
        from mcp import Client

        target = self._server_target()
        async with Client(target) as client:
            result = await client.list_tools()
            return [
                MCPToolInfo(name=t.name, description=t.description or "", input_schema=t.input_schema or {})
                for t in result.tools
            ]

    async def _call_tool_async(self, name: str, arguments: dict[str, Any]) -> MCPCallResult:
        from mcp import Client
        from mcp.types import TextContent

        target = self._server_target()
        async with Client(target) as client:
            result = await client.call_tool(name, arguments)
            text = "\n".join(block.text for block in result.content if isinstance(block, TextContent))
            return MCPCallResult(
                text=text, structured_content=result.structured_content, is_error=bool(result.is_error),
            )

    def list_tools(self) -> list[MCPToolInfo]:
        self._require_configured()
        return asyncio.run(self._list_tools_async())

    def call_tool(
        self, name: str, arguments: dict[str, Any], *,
        confirmation_token: str, session_id: str,
    ) -> MCPCallResult:
        """Invoke an MCP tool. Requires an already-issued, valid confirmation
        token bound to this exact tool name + arguments (see
        thursday.confirmation.issue_confirmation with
        service_id=f"mcp:{name}", text=json.dumps(arguments, sort_keys=True))
        -- never executes without one, regardless of what the tool claims to
        do, since a generic MCP server's semantics can't be known in advance.

        The token is also single-use: it's claimed through
        thursday.action_receipts.claim_action (the same replay defence the
        macro and plan-resume paths use), so a captured token can't re-fire
        the same external tool call repeatedly inside its 300s TTL. A
        security review on 2026-09-08 flagged verify-without-claim as a
        latent replay hole here -- harmless while this module had no callers,
        but exactly the kind of thing that must already be right before a
        real external platform is wired up behind it.
        """
        self._require_configured()
        service_id = f"mcp:{name}"
        text = json.dumps(arguments, sort_keys=True)
        if not verify_confirmation(confirmation_token, session_id=session_id, service_id=service_id, text=text):
            raise MCPConfirmationRequired(
                f"call_tool({name!r}) requires a valid confirmation token bound to "
                f"these exact arguments -- none was provided, it expired, or it "
                f"doesn't match this tool/argument combination."
            )

        from thursday.action_receipts import claim_action, receipt_id_for_token

        claim = claim_action(
            receipt_id_for_token(confirmation_token),
            session_id=session_id,
            service_id=service_id,
            text=text,
        )
        if not claim.claimed:
            raise MCPConfirmationRequired(
                f"call_tool({name!r}) was already executed with this confirmation "
                f"token (receipt {claim.receipt.receipt_id}). Confirmation tokens "
                f"are single-use -- issue a new one to run it again."
            )
        return asyncio.run(self._call_tool_async(name, arguments))

    def health_check(self, timeout: float = 5.0) -> bool:
        if not is_configured():
            return False
        try:
            self.list_tools()
            return True
        except MCPUnavailable:
            return False
