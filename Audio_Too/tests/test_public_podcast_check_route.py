"""Tests for POST /api/public/podcast-check in business/app/public_routes.py.

Covers the route dispatch layer (rate limiting, error handling, log_event)
that sits in front of mix_review.handle_multipart_podcast_check -- that
function's own behaviour is covered separately in tests/mix/test_mix_review.py.
"""

from __future__ import annotations

import math
import struct
import sys
import wave
from io import BytesIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

import db  # noqa: E402
import enquiry_guard  # noqa: E402
import public_routes  # noqa: E402


@pytest.fixture(autouse=True)
def _use_temp_db(monkeypatch, tmp_path):
    # A successful podcast-check now persists a row (podcast_report_store,
    # migration 016) so it can be shared via a signed-token link. Without
    # this redirect these tests would write real rows into the developer's
    # actual data/audio_too.db -- the exact class of bug found and fixed
    # earlier this session in benchmark_routes.py.
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    db.init_db()


def sine_wav(*, frequency: float = 200.0, seconds: float = 1.0, sample_rate: int = 8000) -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(int(seconds * sample_rate)):
            value = int(0.2 * 32767 * math.sin(2 * math.pi * frequency * index / sample_rate))
            wav.writeframesraw(struct.pack("<h", value))
    return buffer.getvalue()


def _multipart_body(boundary: str, wav_bytes: bytes, *, target: str | None = None) -> bytes:
    parts = b""
    if target is not None:
        parts += (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="target"\r\n\r\n'
            f"{target}\r\n"
        ).encode("utf-8")
    parts += (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="episode.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n"
    ).encode("utf-8") + wav_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return parts


class FakeHandler:
    def __init__(self, body: bytes, content_type: str, client_ip: str) -> None:
        self._body = body
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        self.client_address = (client_ip, 12345)
        self.status = 0
        self.payload: dict = {}

    def read_body_bytes(self) -> bytes:
        return self._body

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload


def _events(log: list) -> callable:
    def log_event(event: str, detail: str, source: str) -> None:
        log.append((event, detail, source))
    return log_event


@pytest.fixture(autouse=True)
def _clear_podcast_rate_limit():
    yield
    for ip in ("1.2.3.4", "5.6.7.8", "9.9.9.9"):
        enquiry_guard.clear_rate_limit((ip, 0), "public_podcast_check")


def test_podcast_check_route_returns_a_report_for_a_valid_upload() -> None:
    boundary = "route-boundary"
    body = _multipart_body(boundary, sine_wav(), target="spotify")
    handler = FakeHandler(body, f"multipart/form-data; boundary={boundary}", "1.2.3.4")
    log = []

    handled = public_routes.handle_post(handler, "/api/public/podcast-check", log_event=_events(log))

    assert handled is True
    assert handler.status == 200
    assert handler.payload["ok"] is True
    assert "report" in handler.payload
    assert log and log[0][0] == "public_podcast_check"

    # Persisted with a shareable signed-token link -- the "like Mix Doctor"
    # treatment (plan.md's own NEXT item), so the report can be revisited.
    import podcast_report_tokens
    report_id = handler.payload["id"]
    token = handler.payload["token"]
    assert podcast_report_tokens.verify_podcast_report_token(report_id, token)
    assert handler.payload["report_path"] == f"/podcast-report/{report_id}?token={token}"


def test_podcast_check_route_rejects_missing_file_with_400() -> None:
    boundary = "route-boundary-2"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="target"\r\n\r\n'
        "apple\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    handler = FakeHandler(body, f"multipart/form-data; boundary={boundary}", "5.6.7.8")
    log = []

    handled = public_routes.handle_post(handler, "/api/public/podcast-check", log_event=_events(log))

    assert handled is True
    assert handler.status == 400
    assert handler.payload["ok"] is False
    assert not log


def test_podcast_check_route_is_rate_limited() -> None:
    boundary = "route-boundary-3"
    body = _multipart_body(boundary, sine_wav())
    content_type = f"multipart/form-data; boundary={boundary}"
    log = []

    max_attempts, _window = enquiry_guard.RATE_LIMITS["public_podcast_check"]
    for _ in range(max_attempts):
        handler = FakeHandler(body, content_type, "9.9.9.9")
        public_routes.handle_post(handler, "/api/public/podcast-check", log_event=_events(log))

    limited_handler = FakeHandler(body, content_type, "9.9.9.9")
    handled = public_routes.handle_post(limited_handler, "/api/public/podcast-check", log_event=_events(log))

    assert handled is True
    assert limited_handler.status == 429
