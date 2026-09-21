from __future__ import annotations

import sys

import pytest

from kenn.core.mcp_stdio import MCPTransportError, StdioMCPToolCaller


def test_stdio_client_initializes_calls_allowlisted_tool_and_closes(tmp_path) -> None:
    server = tmp_path / "fake_mcp_server.py"
    server.write_text(
        """
import json
import sys

for line in sys.stdin:
    message = json.loads(line)
    if message.get("method") == "notifications/initialized":
        continue
    request_id = message["id"]
    if message["method"] == "initialize":
        result = {
            "protocolVersion": message["params"]["protocolVersion"],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake", "version": "1"},
        }
    elif message["method"] == "tools/call":
        result = {
            "content": [{"type": "text", "text": "ignored"}],
            "structuredContent": {
                "ok": True,
                "data": {
                    "tool": message["params"]["name"],
                    "arguments": message["params"]["arguments"],
                },
            },
        }
    else:
        result = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\\n")
    sys.stdout.flush()
""".lstrip(),
        encoding="utf-8",
    )
    caller = StdioMCPToolCaller(
        [sys.executable, str(server)],
        allowed_tools=frozenset({"read_session"}),
        timeout_seconds=2.0,
    )
    try:
        assert caller("read_session", {"detail": "full"}) == {
            "ok": True,
            "data": {"tool": "read_session", "arguments": {"detail": "full"}},
        }
        with pytest.raises(MCPTransportError, match="outside KENN's allowlist"):
            caller("delete_track", {"trackIndex": 0})
    finally:
        caller.close()


def test_stdio_client_reports_tool_errors(tmp_path) -> None:
    server = tmp_path / "failing_mcp_server.py"
    server.write_text(
        """
import json
import sys

for line in sys.stdin:
    message = json.loads(line)
    if message.get("method") == "notifications/initialized":
        continue
    request_id = message["id"]
    if message["method"] == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "fake", "version": "1"}}
    else:
        result = {"isError": True, "content": [{"type": "text", "text": "Live is offline"}]}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\\n")
    sys.stdout.flush()
""".lstrip(),
        encoding="utf-8",
    )
    caller = StdioMCPToolCaller(
        [sys.executable, str(server)],
        allowed_tools=frozenset({"ableton_status"}),
        timeout_seconds=2.0,
    )
    try:
        with pytest.raises(MCPTransportError, match="Live is offline"):
            caller("ableton_status", {})
    finally:
        caller.close()


def test_stdio_client_recovers_after_failed_initialization(tmp_path) -> None:
    marker = tmp_path / "first_start_failed"
    server = tmp_path / "recovering_mcp_server.py"
    server.write_text(
        f"""
import json
from pathlib import Path
import sys

marker = Path({str(marker)!r})
if not marker.exists():
    marker.touch()
    raise SystemExit(1)

for line in sys.stdin:
    message = json.loads(line)
    if message.get("method") == "notifications/initialized":
        continue
    request_id = message["id"]
    if message["method"] == "initialize":
        result = {{"protocolVersion": "2025-06-18", "capabilities": {{}}, "serverInfo": {{"name": "fake", "version": "1"}}}}
    else:
        result = {{"structuredContent": {{"ok": True, "data": {{"connected": True}}}}}}
    sys.stdout.write(json.dumps({{"jsonrpc": "2.0", "id": request_id, "result": result}}) + "\\n")
    sys.stdout.flush()
""".lstrip(),
        encoding="utf-8",
    )
    caller = StdioMCPToolCaller(
        [sys.executable, str(server)],
        allowed_tools=frozenset({"ableton_status"}),
        timeout_seconds=2.0,
    )
    try:
        with pytest.raises(MCPTransportError, match="response pipe closed"):
            caller("ableton_status", {})
        assert caller("ableton_status", {}) == {
            "ok": True,
            "data": {"connected": True},
        }
    finally:
        caller.close()
