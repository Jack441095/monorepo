"""Tests for POST /api/public/mix-doctor in business/app/public_routes.py.

handle_multipart_review's own upload/analysis/DB behaviour is exercised
elsewhere (the dashboard route at /api/admin/mix-review uses the same
function) -- this covers the route-dispatch layer this public endpoint
adds on top: rate limiting, minting a shareable signed-token report link
on success, and not leaking a token on failure. Matches the precedent in
tests/ableton/test_ableton_server_feedback.py of monkeypatching
mix_review.handle_multipart_review rather than re-exercising the real
upload/analysis pipeline in a route-dispatch test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

import enquiry_guard  # noqa: E402
import mix_report_tokens  # noqa: E402
import public_routes  # noqa: E402


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
def _clear_mix_doctor_rate_limit():
    yield
    for ip in ("1.2.3.4", "5.6.7.8", "9.9.9.9"):
        enquiry_guard.clear_rate_limit((ip, 0), "public_mix_doctor")


def test_mix_doctor_route_mints_a_shareable_report_link_on_success(monkeypatch) -> None:
    monkeypatch.setattr(
        public_routes.mix_review, "handle_multipart_review",
        lambda content_type, body: {"ok": True, "id": "rev-abc12345", "status": "pending"},
    )
    handler = FakeHandler(b"fake-multipart-body", "multipart/form-data; boundary=x", "1.2.3.4")
    log = []

    handled = public_routes.handle_post(handler, "/api/public/mix-doctor", log_event=_events(log))

    assert handled is True
    assert handler.status == 201
    assert handler.payload["ok"] is True
    assert handler.payload["id"] == "rev-abc12345"
    token = handler.payload["token"]
    assert mix_report_tokens.verify_report_token("rev-abc12345", token)
    assert handler.payload["report_path"] == f"/mix-report/rev-abc12345?token={token}"
    assert handler.payload["status_path"] == f"/mix-report/rev-abc12345/status?token={token}"
    assert log and log[0] == ("public_mix_doctor_upload", "rev-abc12345", "website")


def test_mix_doctor_route_does_not_mint_a_token_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        public_routes.mix_review, "handle_multipart_review",
        lambda content_type, body: {"ok": False, "error": "Missing file field."},
    )
    handler = FakeHandler(b"", "multipart/form-data; boundary=x", "5.6.7.8")
    log = []

    handled = public_routes.handle_post(handler, "/api/public/mix-doctor", log_event=_events(log))

    assert handled is True
    assert handler.status == 400
    assert "token" not in handler.payload
    assert not log


def test_mix_doctor_route_500s_on_unexpected_exception(monkeypatch) -> None:
    def _boom(content_type, body):
        raise RuntimeError("decode exploded")

    monkeypatch.setattr(public_routes.mix_review, "handle_multipart_review", _boom)
    handler = FakeHandler(b"garbage", "multipart/form-data; boundary=x", "9.9.9.9")

    handled = public_routes.handle_post(handler, "/api/public/mix-doctor", log_event=_events([]))

    assert handled is True
    assert handler.status == 500


def test_mix_doctor_route_is_rate_limited(monkeypatch) -> None:
    monkeypatch.setattr(
        public_routes.mix_review, "handle_multipart_review",
        lambda content_type, body: {"ok": True, "id": "rev-x", "status": "pending"},
    )
    max_attempts, _window = enquiry_guard.RATE_LIMITS["public_mix_doctor"]
    for _ in range(max_attempts):
        handler = FakeHandler(b"body", "multipart/form-data; boundary=x", "1.2.3.4")
        public_routes.handle_post(handler, "/api/public/mix-doctor", log_event=_events([]))

    limited_handler = FakeHandler(b"body", "multipart/form-data; boundary=x", "1.2.3.4")
    handled = public_routes.handle_post(limited_handler, "/api/public/mix-doctor", log_event=_events([]))

    assert handled is True
    assert limited_handler.status == 429
