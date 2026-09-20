"""Local NITE Runtime POC (Phase 4C).

Unix-domain-socket JSON service exposing registered capabilities locally.
Local-only by construction: owner-only socket permissions, no TCP. Versioned
length-prefixed JSON envelope; bounded message size; structured errors;
graceful lifecycle.

Threat model: single-user macOS machine. Socket file permissions (0600) are
the V1 authentication boundary; a per-install token can be added later without
a protocol change.
"""

from __future__ import annotations

import json
import os
import socket
import struct
import threading
from pathlib import Path

from nite_ai import __version__
from nite_ai.contracts import AgentRequest
from nite_ai.errors import ErrorCategory
from nite_ai.permissions import Permission

PROTOCOL_VERSION = "1.0"
MAX_MESSAGE_BYTES = 1_000_000
RECV_TIMEOUT_SECONDS = 30.0


class RuntimeUnavailable(ConnectionError):
    """The runtime socket could not be reached (missing, refused, path too long, ...)."""


def _envelope_ok(request_id: str, payload: dict) -> dict:
    return {"protocol_version": PROTOCOL_VERSION, "request_id": request_id,
            "status": "success", "payload": payload, "error": None}


def _envelope_err(request_id: str, code: str, message: str) -> dict:
    return {"protocol_version": PROTOCOL_VERSION, "request_id": request_id,
            "status": "failed", "payload": {},
            "error": {"code": code, "message": message}}


def _recv_exact(conn: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = conn.recv(min(remaining, 65536))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class LocalRuntime:
    """Single-owner local intelligence runtime."""

    def __init__(self, adapter, registry, socket_path) -> None:
        self.adapter = adapter
        self.registry = registry
        self.socket_path = Path(socket_path)
        self._sock: socket.socket | None = None
        self._serve_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.platform_version = __version__
        self.requests_served = 0

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self._sock is not None:
            raise RuntimeError("runtime already started")
        path = self.socket_path
        if path.exists():
            if self._probe_stale(path):
                raise RuntimeError(f"another runtime instance owns {path}")
            path.unlink()  # stale socket from a crashed previous instance
        path.parent.mkdir(parents=True, exist_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))
        os.chmod(str(path), 0o600)  # owner-only — the V1 auth boundary
        server.listen(4)
        server.settimeout(0.2)
        self._sock = server
        self._stop.clear()
        self._serve_thread = threading.Thread(target=self._serve_loop, daemon=True)
        self._serve_thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        if self._serve_thread is not None:
            self._serve_thread.join(timeout=5)
            self._serve_thread = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        if self.socket_path.exists():
            self.socket_path.unlink()

    @staticmethod
    def _probe_stale(path: Path) -> bool:
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(1.0)
        try:
            probe.connect(str(path))
            return True  # something alive is listening — not ours to remove
        except OSError:
            return False
        finally:
            probe.close()

    def _serve_loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                conn.settimeout(RECV_TIMEOUT_SECONDS)
                response = self._serve_connection(conn)
                raw = json.dumps(response).encode()
                conn.sendall(struct.pack(">I", len(raw)) + raw)
            except Exception:
                pass  # one bad exchange must never kill the serve thread
            finally:
                conn.close()

    def _serve_connection(self, conn: socket.socket) -> dict:
        size_raw = _recv_exact(conn, 4)
        if len(size_raw) < 4:
            return _envelope_err("unknown", "malformed_request", "missing length prefix")
        (size,) = struct.unpack(">I", size_raw)
        if size > MAX_MESSAGE_BYTES:
            return _envelope_err("unknown", "oversized_request",
                                 f"request exceeds {MAX_MESSAGE_BYTES} bytes")
        body = _recv_exact(conn, size)
        try:
            envelope = json.loads(body)
        except json.JSONDecodeError as exc:
            return _envelope_err("unknown", "malformed_request", f"invalid JSON: {exc}")
        self.requests_served += 1
        return self.handle_envelope(envelope)

    # ------------------------------------------------------------- dispatch
    def handle_envelope(self, envelope: dict) -> dict:
        if not isinstance(envelope, dict):
            return _envelope_err("unknown", "malformed_request", "envelope must be an object")
        version = envelope.get("protocol_version")
        request_id = str(envelope.get("request_id") or "unknown")
        if version != PROTOCOL_VERSION:
            return _envelope_err(request_id, "protocol_mismatch",
                                 f"client protocol {version!r} != server {PROTOCOL_VERSION!r}")
        operation = str(envelope.get("operation") or "")
        if operation == "handshake":
            return _envelope_ok(request_id, {
                "platform_version": self.platform_version,
                "protocol_version": PROTOCOL_VERSION,
                "capabilities": sorted(d.capability_id for d in self.registry.enumerate()),
            })
        payload = envelope.get("payload") or {}
        trace = envelope.get("trace") or {}
        granted = tuple(Permission(p) for p in (payload.get("granted_permissions") or []))
        request = AgentRequest(
            request_id=request_id,
            trace_id=str(trace.get("trace_id") or request_id),
            capability_id=operation,
            payload=payload.get("data") or {},
            granted_permissions=granted,
        )
        result = self.adapter.dispatch(request)
        if not result.ok:
            return _envelope_err(request_id, result.error.category.value,
                                 result.error.message)
        return _envelope_ok(request_id, {
            "result": result.result or {},
            "evidence": result.evidence.payload() if result.evidence else None,
            "warnings": list(result.warnings),
            "trace_id": request.trace_id,
        })


class RuntimeClient:
    """Minimal client used by tests and the CLI."""

    def __init__(self, socket_path: Path | str, timeout: float = 10.0) -> None:
        self.socket_path = Path(socket_path)
        self.timeout = timeout

    def call(self, envelope: dict) -> dict:
        raw = json.dumps(envelope).encode()
        if len(raw) > MAX_MESSAGE_BYTES:
            raise ValueError("request too large")
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(self.timeout)
        try:
            try:
                conn.connect(str(self.socket_path))
            except OSError as exc:
                # Any connect-phase failure (missing socket, refused, path too
                # long, permission denied, ...) means the runtime is unreachable.
                raise RuntimeUnavailable(
                    f"cannot reach runtime at {self.socket_path}: {exc}"
                ) from exc
            conn.sendall(struct.pack(">I", len(raw)) + raw)
            size_raw = _recv_exact(conn, 4)
            if len(size_raw) < 4:
                raise ConnectionError("no response from runtime")
            (size,) = struct.unpack(">I", size_raw)
            body = _recv_exact(conn, size)
            return json.loads(body)
        finally:
            conn.close()


__all__ = ["LocalRuntime", "RuntimeClient", "RuntimeUnavailable",
           "MAX_MESSAGE_BYTES", "PROTOCOL_VERSION"]
