"""Tests for thursday/mcp_client.py -- the generic, disabled-by-default MCP
client capability. No specific external platform is wired up yet, so most
tests here cover the verifiable, safety-critical parts: disabled-by-default
behavior, and that call_tool() never executes without a valid, matching
confirmation token, using mocks for the transport layer.

test_real_mcp_server_end_to_end below is different: it launches an actual
`mcp` SDK server (tests/fixtures/toy_mcp_server.py) as a real subprocess and
talks to it for real -- this is what caught the module's original code
being written against the SDK's legacy v1 API shape (ClientSession/
stdio_client/sse_client) when `pip install mcp` today installs v2, whose
Client/StdioServerParameters shape is different. Skipped if `mcp` isn't
installed (it's an optional, lazily-imported extra, same as every other
cross-repo integration in this codebase).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from thursday import confirmation
from thursday.mcp_client import (
    MCPConfirmationRequired,
    MCPToolProvider,
    MCPUnavailable,
    is_configured,
)

try:
    import mcp  # noqa: F401
    _MCP_INSTALLED = True
except ImportError:
    _MCP_INSTALLED = False


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    monkeypatch.delenv("THURSDAY_MCP_SERVER_COMMAND", raising=False)
    monkeypatch.delenv("THURSDAY_MCP_SERVER_URL", raising=False)
    # call_tool now claims the confirmation token through action_receipts
    # (single-use replay defence) -- point that at a per-test SQLite file so
    # tests never touch a real installation's receipts DB and never leak
    # claims into each other.
    monkeypatch.setenv("THURSDAY_ACTION_RECEIPTS_DB", str(tmp_path / "receipts.sqlite3"))
    yield


def test_is_configured_false_by_default():
    assert is_configured() is False


def test_is_configured_true_with_command_env_var(monkeypatch):
    monkeypatch.setenv("THURSDAY_MCP_SERVER_COMMAND", "npx some-server")
    assert is_configured() is True


def test_is_configured_true_with_url_env_var(monkeypatch):
    monkeypatch.setenv("THURSDAY_MCP_SERVER_URL", "https://example.com/mcp")
    assert is_configured() is True


def test_list_tools_raises_clear_error_when_unconfigured():
    provider = MCPToolProvider()
    with pytest.raises(MCPUnavailable, match="No MCP server configured"):
        provider.list_tools()


def test_call_tool_raises_clear_error_when_unconfigured():
    provider = MCPToolProvider()
    with pytest.raises(MCPUnavailable):
        provider.call_tool("post", {"text": "hi"}, confirmation_token="bogus", session_id="s1")


def test_health_check_false_when_unconfigured():
    assert MCPToolProvider().health_check() is False


def test_call_tool_refuses_without_a_confirmation_token(monkeypatch):
    monkeypatch.setenv("THURSDAY_MCP_SERVER_COMMAND", "npx some-server")
    provider = MCPToolProvider()
    with pytest.raises(MCPConfirmationRequired):
        provider.call_tool("post", {"text": "hi"}, confirmation_token="not-a-real-token", session_id="s1")


def test_call_tool_refuses_a_token_issued_for_different_arguments(monkeypatch):
    monkeypatch.setenv("THURSDAY_MCP_SERVER_COMMAND", "npx some-server")
    provider = MCPToolProvider()
    import json
    token, _ = confirmation.issue_confirmation(
        session_id="s1", service_id="mcp:post", text=json.dumps({"text": "original"}, sort_keys=True),
    )
    with pytest.raises(MCPConfirmationRequired):
        provider.call_tool("post", {"text": "different"}, confirmation_token=token, session_id="s1")


def test_call_tool_refuses_a_token_issued_for_a_different_tool(monkeypatch):
    monkeypatch.setenv("THURSDAY_MCP_SERVER_COMMAND", "npx some-server")
    provider = MCPToolProvider()
    import json
    token, _ = confirmation.issue_confirmation(
        session_id="s1", service_id="mcp:campaign", text=json.dumps({"text": "hi"}, sort_keys=True),
    )
    with pytest.raises(MCPConfirmationRequired):
        provider.call_tool("post", {"text": "hi"}, confirmation_token=token, session_id="s1")


def test_call_tool_proceeds_to_transport_with_a_valid_matching_token(monkeypatch):
    """A valid token should pass the confirmation gate and reach the (here,
    mocked-out) transport layer -- confirms the gate isn't overly strict,
    only the transport/SDK call itself is unverified in this environment."""
    monkeypatch.setenv("THURSDAY_MCP_SERVER_COMMAND", "npx some-server")
    provider = MCPToolProvider()

    async def _fake_call_tool_async(name, args):
        return "mock-result"

    monkeypatch.setattr(provider, "_call_tool_async", _fake_call_tool_async)

    import json
    args = {"text": "hi"}
    token, _ = confirmation.issue_confirmation(
        session_id="s1", service_id="mcp:post", text=json.dumps(args, sort_keys=True),
    )
    result = provider.call_tool("post", args, confirmation_token=token, session_id="s1")
    assert result == "mock-result"


def test_call_tool_token_is_single_use(monkeypatch):
    """Replay defence, added after a 2026-09-08 security review: the first
    call with a valid token executes, a second call with the SAME token is
    refused even though the token itself is still cryptographically valid
    and unexpired."""
    monkeypatch.setenv("THURSDAY_MCP_SERVER_COMMAND", "npx some-server")
    provider = MCPToolProvider()
    calls = []

    async def _fake_call_tool_async(name, args):
        calls.append(name)
        return "mock-result"

    monkeypatch.setattr(provider, "_call_tool_async", _fake_call_tool_async)

    args = {"text": "publish this"}
    token, _ = confirmation.issue_confirmation(
        session_id="s1", service_id="mcp:post", text=json.dumps(args, sort_keys=True),
    )
    provider.call_tool("post", args, confirmation_token=token, session_id="s1")
    assert calls == ["post"]

    with pytest.raises(MCPConfirmationRequired, match="single-use"):
        provider.call_tool("post", args, confirmation_token=token, session_id="s1")
    assert calls == ["post"]  # the replay never reached the transport


@pytest.mark.skipif(not _MCP_INSTALLED, reason="mcp SDK not installed (optional extra)")
def test_real_mcp_server_end_to_end(monkeypatch):
    """Launches tests/fixtures/toy_mcp_server.py as a real subprocess and
    talks to it through the real mcp SDK -- no mocks. This is the test that
    would have caught this module originally being written against the
    SDK's legacy v1 shape."""
    server_path = Path(__file__).parent / "fixtures" / "toy_mcp_server.py"
    monkeypatch.setenv("THURSDAY_MCP_SERVER_COMMAND", f"{sys.executable} {server_path}")

    provider = MCPToolProvider()
    tools = provider.list_tools()
    assert [t.name for t in tools] == ["draft_post"]
    assert "social media post" in tools[0].description.lower()

    args = {"platform": "instagram", "topic": "new studio hours"}
    token, _ = confirmation.issue_confirmation(
        session_id="s1", service_id="mcp:draft_post", text=json.dumps(args, sort_keys=True),
    )
    result = provider.call_tool("draft_post", args, confirmation_token=token, session_id="s1")
    assert result.is_error is False
    assert "instagram" in result.text.lower()
    assert "new studio hours" in result.text.lower()
