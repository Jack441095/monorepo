"""Small synchronous MCP stdio client for local Live control providers.

The client deliberately implements only the MCP lifecycle and ``tools/call``
surface KENN needs.  It launches a configured command directly (never through
a shell), keeps one process alive for the backend lifetime, serializes calls,
and rejects every tool outside an explicit allowlist.
"""

from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
from threading import Lock, Thread
from typing import Any, Mapping, Sequence


DEFAULT_PROTOCOL_VERSION = "2025-06-18"
MAX_MESSAGE_BYTES = 4 * 1024 * 1024


class MCPTransportError(RuntimeError):
    """Raised when a configured MCP process cannot complete a protocol call."""


class StdioMCPToolCaller:
    """Call an allowlisted set of tools on one local MCP stdio process."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        allowed_tools: frozenset[str],
        cwd: str | Path | None = None,
        timeout_seconds: float = 8.0,
        protocol_version: str = DEFAULT_PROTOCOL_VERSION,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        normalized = tuple(str(part) for part in command if str(part))
        if not normalized:
            raise ValueError("MCP command must contain an executable.")
        if not allowed_tools:
            raise ValueError("MCP tool allowlist must not be empty.")
        if timeout_seconds <= 0:
            raise ValueError("MCP timeout must be positive.")

        self.command = normalized
        self.allowed_tools = allowed_tools
        self.cwd = str(Path(cwd).expanduser().resolve()) if cwd else None
        self.timeout_seconds = float(timeout_seconds)
        self.protocol_version = str(protocol_version)
        self.environment = dict(environment) if environment is not None else None

        self._lock = Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._stdout: Queue[bytes | None] = Queue()
        self._stderr_tail: deque[str] = deque(maxlen=20)
        self._next_id = 1
        self._closed = False

    def _start_reader_threads(self, process: subprocess.Popen[bytes]) -> None:
        assert process.stdout is not None
        assert process.stderr is not None
        stdout_queue = self._stdout
        stderr_tail = self._stderr_tail

        def read_stdout() -> None:
            while True:
                raw = process.stdout.readline(MAX_MESSAGE_BYTES + 1)
                if not raw:
                    stdout_queue.put(None)
                    return
                stdout_queue.put(raw)

        def read_stderr() -> None:
            for raw in process.stderr:
                stderr_tail.append(raw.decode("utf-8", errors="replace").rstrip())

        Thread(target=read_stdout, name="kenn-mcp-stdout", daemon=True).start()
        Thread(target=read_stderr, name="kenn-mcp-stderr", daemon=True).start()

    def _ensure_started(self) -> None:
        if self._closed:
            raise MCPTransportError("MCP client is closed.")
        if self._process is not None:
            if self._process.poll() is None:
                return
            raise MCPTransportError(self._exit_message("MCP process exited"))

        environment = os.environ.copy()
        if self.environment:
            environment.update(self.environment)
        # Each process needs fresh buffers.  Otherwise an EOF marker left by a
        # failed initialization can poison a later recovery attempt.
        self._stdout = Queue()
        self._stderr_tail = deque(maxlen=20)
        try:
            process = subprocess.Popen(
                self.command,
                cwd=self.cwd,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                bufsize=0,
            )
        except OSError as exc:
            raise MCPTransportError(f"Unable to start MCP command: {exc}") from exc

        self._process = process
        self._start_reader_threads(process)
        try:
            self._exchange(
                "initialize",
                {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": "kenn", "version": "1"},
                },
            )
            self._write_message(
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
            )
        except Exception:
            self._stop_process()
            raise

    def _write_message(self, payload: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise MCPTransportError(self._exit_message("MCP process is unavailable"))
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
        if len(encoded) > MAX_MESSAGE_BYTES:
            raise MCPTransportError("MCP request exceeds the local message limit.")
        try:
            process.stdin.write(encoded)
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise MCPTransportError(self._exit_message("MCP request pipe closed")) from exc

    def _read_response(self, request_id: int) -> dict[str, Any]:
        while True:
            try:
                raw = self._stdout.get(timeout=self.timeout_seconds)
            except Empty as exc:
                raise MCPTransportError(
                    f"MCP request {request_id} timed out after {self.timeout_seconds:.1f}s."
                ) from exc
            if raw is None:
                raise MCPTransportError(self._exit_message("MCP response pipe closed"))
            if len(raw) > MAX_MESSAGE_BYTES:
                raise MCPTransportError("MCP response exceeds the local message limit.")
            try:
                message = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise MCPTransportError("MCP server wrote an invalid JSON response.") from exc
            if not isinstance(message, dict):
                raise MCPTransportError("MCP server wrote a non-object JSON response.")
            if message.get("id") != request_id:
                # Notifications and unrelated server messages do not satisfy a
                # request.  Calls are serialized, so no valid response is lost.
                continue
            if "error" in message:
                error = message.get("error")
                if isinstance(error, dict):
                    detail = str(error.get("message") or error.get("code") or "unknown error")
                else:
                    detail = str(error)
                raise MCPTransportError(f"MCP request failed: {detail}")
            result = message.get("result")
            if not isinstance(result, dict):
                raise MCPTransportError("MCP response has no object result.")
            return result

    def _exchange(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._write_message(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        return self._read_response(request_id)

    def __call__(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name not in self.allowed_tools:
            raise MCPTransportError(f"MCP tool '{tool_name}' is outside KENN's allowlist.")
        if not isinstance(arguments, dict):
            raise TypeError("MCP tool arguments must be an object.")
        with self._lock:
            self._ensure_started()
            result = self._exchange(
                "tools/call", {"name": tool_name, "arguments": dict(arguments)}
            )

        if result.get("isError") is True:
            raise MCPTransportError(self._content_error(result) or f"MCP tool '{tool_name}' failed.")
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict) or item.get("type") != "text":
                    continue
                try:
                    decoded = json.loads(str(item.get("text", "")))
                except json.JSONDecodeError:
                    continue
                if isinstance(decoded, dict):
                    return decoded
        raise MCPTransportError(f"MCP tool '{tool_name}' returned no structured object.")

    @staticmethod
    def _content_error(result: dict[str, Any]) -> str:
        content = result.get("content")
        if not isinstance(content, list):
            return ""
        return " ".join(
            str(item.get("text", "")).strip()
            for item in content
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text")
        ).strip()

    def _exit_message(self, prefix: str) -> str:
        code = self._process.poll() if self._process is not None else None
        suffix = f" (exit {code})" if code is not None else ""
        stderr = " | ".join(self._stderr_tail)
        return f"{prefix}{suffix}{': ' + stderr if stderr else ''}"

    def _stop_process(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._stop_process()


__all__ = [
    "DEFAULT_PROTOCOL_VERSION",
    "MAX_MESSAGE_BYTES",
    "MCPTransportError",
    "StdioMCPToolCaller",
]
