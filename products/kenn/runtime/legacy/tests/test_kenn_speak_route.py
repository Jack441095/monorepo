"""Tests for KENN's own /api/speak TTS route -- reuses Thursday's existing
Kokoro synthesis pipeline directly rather than a second one (per the
"reuse, don't build a second TTS path" decision, Phase after
docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md's tool-registry work)."""

from __future__ import annotations

import sys
import types
from io import BytesIO
from pathlib import Path

LM = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn"
sys.path.insert(0, str(LM))

import server  # noqa: E402


class FakeHandler:
    def __init__(self, path: str, body: bytes) -> None:
        self.path = path
        self.status = 0
        self.payload = None
        self.body = b""
        self.content_type = ""
        self.headers = {"Content-Length": str(len(body))}
        self.rfile = BytesIO(body)

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload

    def send_bytes(self, status: int, body: bytes, content_type: str, *, filename: str = "") -> None:
        self.status = status
        self.body = body
        self.content_type = content_type

    def allowed_cors_origin(self) -> str:
        return ""

    def enforce_rate_limit(self, _bucket: str) -> bool:
        return True


def _post(body: dict) -> FakeHandler:
    import json as _json

    payload = _json.dumps(body).encode("utf-8")
    handler = FakeHandler("/api/speak", payload)
    server.Handler.do_POST(handler)
    return handler


def test_speak_returns_wav_bytes_on_success(monkeypatch) -> None:
    captured = {}

    def fake_synthesise_isolated(text, voice=None, speed=None):
        captured["text"] = text
        captured["voice"] = voice
        return b"RIFF-fake-wav-bytes"

    fake_module = types.SimpleNamespace(
        synthesise_isolated=fake_synthesise_isolated, KENN_VOICE="am_onyx"
    )
    monkeypatch.setitem(sys.modules, "thursday.voice_output", fake_module)

    handler = _post({"text": "This will boost the highshelf EQ."})
    assert handler.status == 200
    assert handler.body == b"RIFF-fake-wav-bytes"
    assert handler.content_type == "audio/wav"
    assert captured["text"] == "This will boost the highshelf EQ."
    assert captured["voice"] == "am_onyx"


def test_speak_requires_text() -> None:
    handler = _post({"text": ""})
    assert handler.status == 400


def test_speak_returns_503_when_tts_unavailable(monkeypatch) -> None:
    fake_module = types.SimpleNamespace(
        synthesise_isolated=lambda text, voice=None, speed=None: None, KENN_VOICE="am_onyx"
    )
    monkeypatch.setitem(sys.modules, "thursday.voice_output", fake_module)

    handler = _post({"text": "hello"})
    assert handler.status == 503


def test_speak_returns_500_on_synthesis_exception(monkeypatch) -> None:
    def boom(text, voice=None, speed=None):
        raise RuntimeError("kokoro exploded")

    fake_module = types.SimpleNamespace(synthesise_isolated=boom, KENN_VOICE="am_onyx")
    monkeypatch.setitem(sys.modules, "thursday.voice_output", fake_module)

    handler = _post({"text": "hello"})
    assert handler.status == 500
    assert "kokoro exploded" in handler.payload["error"]
