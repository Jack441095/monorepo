"""Unit tests for KENN Public Beta API endpoints (/health, /chat, /mix-review, /feedback)."""

from __future__ import annotations

import io
import struct
import wave
from fastapi.testclient import TestClient
from app import app, reset_rate_limit_for_tests


client = TestClient(app)


def setup_function():
    reset_rate_limit_for_tests()


def create_synthetic_wav_bytes(duration_sec: float = 1.0, num_channels: int = 2) -> bytes:
    buf = io.BytesIO()
    framerate = 44100
    n_frames = int(framerate * duration_sec)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(framerate)
        # Generate 1 second of silence
        data = struct.pack(f"<{n_frames * num_channels}h", *([0] * (n_frames * num_channels)))
        wf.writeframes(data)
    return buf.getvalue()


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "ok"
    assert data["service"] == "kenn-public-api"
    assert data["version"] == "1.0.0-beta"
    assert data["schema_version"] == "kenn.public_api.v1"
    assert "privacy" in data
    assert data["features"]["chat"] is True
    assert data["features"]["mix_review"] is True
    assert data["features"]["automix"] is False


def test_chat_endpoint_valid_question():
    req_payload = {
        "question": "How do I fix harsh vocals?",
        "history": [],
    }
    resp = client.post("/chat", json=req_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "request_id" in data
    assert data["schema_version"] == "kenn.public_api.v1"
    assert "data" in data


def test_chat_endpoint_out_of_scope():
    req_payload = {
        "question": "Who invented mixing?",
        "history": [],
    }
    resp = client.post("/chat", json=req_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["data"]["found"] is False


def test_mix_review_endpoint_success():
    wav_bytes = create_synthetic_wav_bytes(duration_sec=1.5, num_channels=2)
    resp = client.post(
        "/mix-review",
        files={"file": ("test_mix.wav", wav_bytes, "audio/wav")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "request_id" in data
    assert data["schema_version"] == "kenn.public_api.v1"
    assert "receipt" in data
    receipt = data["receipt"]
    assert receipt["input_context"]["format"] == "wav"


def test_mix_review_endpoint_rejects_non_wav():
    resp = client.post(
        "/mix-review",
        files={"file": ("test.mp3", b"ID3 fake mp3 data", "audio/mpeg")},
    )
    assert resp.status_code == 400
    assert "Unsupported file format" in resp.json()["detail"]


def test_feedback_endpoint():
    fb_payload = {
        "request_id": "req-test-12345",
        "rating": 5,
        "comments": "Very helpful EQ advice!",
        "context_type": "chat",
    }
    resp = client.post("/feedback", json=fb_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "feedback_id" in data
    assert data["status"] == "received"
