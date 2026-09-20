"""Tests for the persistent KENN MLX model server wiring in kenn_lm.py.

docs/CAPABILITY_IMPROVEMENTS_2026-07-06.md: kenn_lm.py used to spawn a fresh
subprocess that reloaded the full MLX model from disk on every single
generation call — up to 3x per answer turn with self_correct=True (~1.85s
reload each, measured). kenn_lm_server.py loads the model once and stays
warm; kenn_lm.py now prefers it and falls back to the original per-call
subprocess path whenever the server isn't reachable, so correctness never
depends on the server being up.

These tests use a real toy Unix socket server (not the actual MLX model) to
validate the client-side protocol and fallback behavior fast and
deterministically.
"""

from __future__ import annotations

import json
import socketserver
import sys
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.llm import kenn_lm  # noqa: E402


class _EchoHandler(socketserver.StreamRequestHandler):
    """Toy server: pings succeed, generation jobs echo back a canned answer."""

    def handle(self) -> None:
        line = self.rfile.readline()
        job = json.loads(line.decode("utf-8"))
        if job.get("op") == "ping":
            response = {"ok": True}
        else:
            response = {"ok": True, "text": "canned answer from fake server"}
        self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))


class _ErrorHandler(socketserver.StreamRequestHandler):
    """Toy server that always reports a generation error."""

    def handle(self) -> None:
        self.rfile.readline()
        self.wfile.write((json.dumps({"ok": False, "error": "boom"}) + "\n").encode("utf-8"))


def _short_socket_path() -> Path:
    # AF_UNIX paths are capped at ~104 bytes on macOS/BSD — pytest's tmp_path
    # fixture nests too deep for that in this project, so use /tmp directly.
    return Path(f"/tmp/kenn_lm_test_{uuid.uuid4().hex[:10]}.sock")


def _run_fake_server(handler_cls, socket_path: str) -> socketserver.UnixStreamServer:
    server = socketserver.UnixStreamServer(socket_path, handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_send_to_server_returns_none_when_nothing_listening(monkeypatch) -> None:
    monkeypatch.setattr(kenn_lm, "_SERVER_SOCKET", _short_socket_path())
    result = kenn_lm._send_to_server({"op": "ping"}, connect_timeout=0.2)
    assert result is None


def test_send_to_server_round_trips_with_a_real_socket(monkeypatch) -> None:
    socket_path = str(_short_socket_path())
    server = _run_fake_server(_EchoHandler, socket_path)
    try:
        monkeypatch.setattr(kenn_lm, "_SERVER_SOCKET", Path(socket_path))
        ping = kenn_lm._send_to_server({"op": "ping"}, connect_timeout=1.0)
        assert ping == {"ok": True}

        job = kenn_lm._send_to_server(
            {"messages": [{"role": "user", "content": "hi"}], "max_new_tokens": 10},
            connect_timeout=1.0,
        )
        assert job == {"ok": True, "text": "canned answer from fake server"}
    finally:
        server.shutdown()
        Path(socket_path).unlink(missing_ok=True)


def test_run_generation_mlx_uses_server_when_available(monkeypatch) -> None:
    socket_path = str(_short_socket_path())
    server = _run_fake_server(_EchoHandler, socket_path)
    try:
        monkeypatch.setattr(kenn_lm, "_SERVER_SOCKET", Path(socket_path))
        lm = kenn_lm.KennLM.__new__(kenn_lm.KennLM)  # skip __init__/real model load
        text = lm._run_generation_mlx([{"role": "user", "content": "hi"}], max_new_tokens=10)
        assert text == "canned answer from fake server"
    finally:
        server.shutdown()
        Path(socket_path).unlink(missing_ok=True)


def test_run_generation_mlx_falls_back_when_server_unreachable(monkeypatch) -> None:
    monkeypatch.setattr(kenn_lm, "_SERVER_SOCKET", _short_socket_path())
    monkeypatch.setattr(kenn_lm, "_ensure_server_started", lambda: None)  # don't actually spawn anything

    called = {}

    def fake_subprocess_path(self, messages, *, max_new_tokens=450):
        called["messages"] = messages
        return "fallback answer"

    monkeypatch.setattr(kenn_lm.KennLM, "_run_generation_mlx_subprocess", fake_subprocess_path)
    lm = kenn_lm.KennLM.__new__(kenn_lm.KennLM)
    text = lm._run_generation_mlx([{"role": "user", "content": "hi"}])
    assert text == "fallback answer"
    assert called["messages"] == [{"role": "user", "content": "hi"}]


def test_run_generation_mlx_falls_back_on_server_error(monkeypatch) -> None:
    """A server that's up but reports a generation error must not surface
    that error directly — retry via the reliable subprocess path instead."""
    socket_path = str(_short_socket_path())
    server = _run_fake_server(_ErrorHandler, socket_path)
    try:
        monkeypatch.setattr(kenn_lm, "_SERVER_SOCKET", Path(socket_path))

        def fake_subprocess_path(self, messages, *, max_new_tokens=450):
            return "fallback answer after server error"

        monkeypatch.setattr(kenn_lm.KennLM, "_run_generation_mlx_subprocess", fake_subprocess_path)
        lm = kenn_lm.KennLM.__new__(kenn_lm.KennLM)
        text = lm._run_generation_mlx([{"role": "user", "content": "hi"}])
        assert text == "fallback answer after server error"
    finally:
        server.shutdown()
        Path(socket_path).unlink(missing_ok=True)


def test_ensure_server_started_only_launches_once(monkeypatch) -> None:
    monkeypatch.setattr(kenn_lm, "_last_start_attempt_time", 0.0)
    calls = []
    monkeypatch.setattr(kenn_lm.subprocess, "Popen", lambda *a, **k: calls.append(1))
    kenn_lm._ensure_server_started()
    kenn_lm._ensure_server_started()
    kenn_lm._ensure_server_started()

    assert len(calls) == 1


class _StreamingEchoHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        line = self.rfile.readline()
        job = json.loads(line.decode("utf-8"))
        if job.get("stream"):
            for t in ["Short", " Answer", ": Use", " 48 kHz."]:
                self.wfile.write((json.dumps({"ok": True, "token": t}) + "\n").encode("utf-8"))
                self.wfile.flush()
            self.wfile.write((json.dumps({"ok": True, "done": True, "text": "Short Answer: Use 48 kHz."}) + "\n").encode("utf-8"))
            self.wfile.flush()
        else:
            self.wfile.write((json.dumps({"ok": True, "text": "Short Answer: Use 48 kHz."}) + "\n").encode("utf-8"))
            self.wfile.flush()


def test_streaming_protocol_yields_tokens(monkeypatch) -> None:
    socket_path = str(_short_socket_path())
    server = _run_fake_server(_StreamingEchoHandler, socket_path)
    try:
        monkeypatch.setattr(kenn_lm, "_SERVER_SOCKET", Path(socket_path))
        chunks = list(kenn_lm._send_to_server_stream({"messages": []}, connect_timeout=0.5))
        assert len(chunks) == 5
        tokens = [c["token"] for c in chunks if "token" in c]
        assert tokens == ["Short", " Answer", ": Use", " 48 kHz."]
        assert chunks[-1]["done"] is True
    finally:
        server.shutdown()
        Path(socket_path).unlink(missing_ok=True)
