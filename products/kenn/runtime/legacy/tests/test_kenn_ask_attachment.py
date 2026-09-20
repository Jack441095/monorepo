"""Tests for POST /api/ask-attachment -- attaching audio directly in the
chat composer instead of the separate upload widget (Jack's decision,
2026-08-05: explicit phrase required, same rule as text-only chat
triggers). Mirrors test_kenn_automix_upload.py's MockHandler pattern."""

from __future__ import annotations

import io
import sys
import types
from pathlib import Path

from kenn import server

WEBSITE = Path(__file__).resolve().parent.parent.parent / "business" / "app"
sys.path.insert(0, str(WEBSITE))


class MockHandler(server.Handler):
    def __init__(self, *, headers: dict | None = None, body: bytes = b""):
        self.headers = headers or {}
        self.client_address = ("127.0.0.1", 0)
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.status = 0
        self.sent_json: dict = {}

    def send_response(self, status: int, message=None) -> None:
        self.status = status

    def send_header(self, name: str, value: str) -> None:
        pass

    def end_headers(self) -> None:
        pass

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.sent_json = payload

    def request_id(self) -> str:
        return "test-req"

    def structured_log(self, *a, **k) -> None:
        pass

    def enforce_rate_limit(self, scope: str) -> bool:
        return True


def _multipart_body(fields: dict[str, tuple[bytes, str] | str], boundary: str = "BOUNDARY") -> bytes:
    parts = []
    for name, value in fields.items():
        if isinstance(value, tuple):
            data, filename = value
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n\r\n'
                .encode() + data + b"\r\n"
            )
        else:
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
            )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts)


def _post(fields: dict) -> MockHandler:
    body = _multipart_body(fields)
    handler = MockHandler(
        headers={"Content-Type": "multipart/form-data; boundary=BOUNDARY", "Content-Length": str(len(body))},
        body=body,
    )
    server.Handler.handle_ask_attachment(handler)
    return handler


def test_rejects_non_multipart_content_type():
    handler = MockHandler(headers={"Content-Type": "application/json", "Content-Length": "2"}, body=b"{}")
    server.Handler.handle_ask_attachment(handler)
    assert handler.status == 400


def test_no_file_attached_is_a_400():
    handler = _post({"question": "run a mix review on this"})
    assert handler.status == 400
    assert "audio" in handler.sent_json["error"].lower()


def test_file_attached_with_no_matching_phrase_asks_for_clarification():
    handler = _post({"question": "hey", "file_0": (b"RIFF....WAVEfake", "track.wav")})
    assert handler.status == 200
    assert handler.sent_json["tool_invoked"] is None
    assert "not sure what you'd like" in handler.sent_json["answer"]


def test_file_attached_with_question_phrasing_does_not_trigger():
    """Same explicit-vs-question rule as text-only triggers -- attaching a
    file doesn't loosen it."""
    handler = _post({
        "question": "how do I run a mix review myself?",
        "file_0": (b"RIFF....WAVEfake", "track.wav"),
    })
    assert handler.sent_json["tool_invoked"] is None


def test_explicit_phrase_with_one_file_invokes_mix_review(monkeypatch):
    monkeypatch.setattr(server, "resolve_session_project", lambda session_id: "kenn-abc")
    captured = {}

    def fake_invoke_tool(name, **kwargs):
        captured["name"] = name
        captured["kwargs"] = kwargs
        return {"ok": True, "id": "review-1", "status": "pending"}

    fake_registry = types.SimpleNamespace(invoke_tool=fake_invoke_tool)
    monkeypatch.setitem(sys.modules, "kenn.core.tool_registry", fake_registry)

    handler = _post({
        "question": "run a mix review on this",
        "session_id": "s1",
        "file_0": (b"RIFF....WAVEfake", "track.wav"),
    })

    assert handler.status == 200
    assert handler.sent_json["tool_invoked"] == "run_mix_review"
    assert "track.wav" in handler.sent_json["answer"]
    assert captured["name"] == "run_mix_review"
    assert captured["kwargs"]["file_bytes"] == b"RIFF....WAVEfake"
    assert captured["kwargs"]["filename"] == "track.wav"
    assert captured["kwargs"]["project_id"] == "kenn-abc"


def test_explicit_phrase_with_multiple_files_invokes_automix(monkeypatch):
    monkeypatch.setattr(server, "resolve_session_project", lambda session_id: "kenn-xyz")
    captured = {}

    def fake_invoke_tool(name, **kwargs):
        captured["name"] = name
        captured["kwargs"] = kwargs
        return {"ok": True, "project_id": "kenn-xyz", "job_id": "job-1", "status": "queued"}

    fake_registry = types.SimpleNamespace(invoke_tool=fake_invoke_tool)
    monkeypatch.setitem(sys.modules, "kenn.core.tool_registry", fake_registry)

    handler = _post({
        "question": "start an automix from these",
        "session_id": "s1",
        "file_0": (b"stem-a-bytes", "a.wav"),
        "file_1": (b"stem-b-bytes", "b.wav"),
    })

    assert handler.status == 200
    assert handler.sent_json["tool_invoked"] == "run_automix"
    assert captured["name"] == "run_automix"
    assert captured["kwargs"]["files"] == [(b"stem-a-bytes", "a.wav"), (b"stem-b-bytes", "b.wav")]
    assert captured["kwargs"]["project_id"] == "kenn-xyz"


def test_failed_tool_call_returns_readable_error(monkeypatch):
    monkeypatch.setattr(server, "resolve_session_project", lambda session_id: "kenn-abc")
    fake_registry = types.SimpleNamespace(
        invoke_tool=lambda name, **kwargs: {"ok": False, "error": "Upload is too large."}
    )
    monkeypatch.setitem(sys.modules, "kenn.core.tool_registry", fake_registry)

    handler = _post({
        "question": "separate this into stems",
        "session_id": "s1",
        "file_0": (b"RIFF....WAVEfake", "track.wav"),
    })

    assert handler.sent_json["tool_invoked"] == "run_stem_separation"
    assert "Upload is too large." in handler.sent_json["answer"]
