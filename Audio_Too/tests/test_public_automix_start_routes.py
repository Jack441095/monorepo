"""Tests for POST /api/public/automix-start + GET .../status.

Mirrors test_public_stem_separate_routes.py's pattern: monkeypatch
automix_public/automix_jobs functions the routes call rather than
re-exercising the real upload/job pipeline (covered on its own by
test_automix_public.py).
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlencode

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import automix_jobs  # noqa: E402
import automix_public  # noqa: E402
import automix_public_tokens  # noqa: E402
import enquiry_guard  # noqa: E402
import public_routes  # noqa: E402
from app.routes.public_api_routes import handle_public_get  # noqa: E402


class FakeHandler:
    def __init__(self, body: bytes = b"", content_type: str = "", client_ip: str = "1.2.3.4") -> None:
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


def _events(log: list):
    def log_event(event: str, detail: str, source: str) -> None:
        log.append((event, detail, source))
    return log_event


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    yield
    for ip in ("1.2.3.4",):
        enquiry_guard.clear_rate_limit((ip, 0), "public_automix_start")


def test_upload_route_returns_202_with_status_link(monkeypatch):
    monkeypatch.setattr(
        public_routes.stem_uploads, "parse_multipart_form",
        lambda content_type, body: {
            "stem_0": b"RIFF....WAVEfake", "stem_0__filename": "bass.wav",
            "stem_1": b"RIFF....WAVEfake2", "stem_1__filename": "vocal.wav",
            "genre": "edm",
        },
    )
    captured = {}

    def fake_start(files, **kw):
        captured["files"] = files
        captured["genre"] = kw.get("genre")
        return {"ok": True, "project_id": "kenn-abc123", "job_id": "job-xyz", "status": "queued"}

    monkeypatch.setattr(automix_public, "start_public_automix", fake_start)
    handler = FakeHandler(b"body", "multipart/form-data; boundary=x")
    log = []

    handled = public_routes.handle_post(handler, "/api/public/automix-start", log_event=_events(log))

    assert handled is True
    assert handler.status == 202
    assert handler.payload["ok"] is True
    assert handler.payload["project_id"] == "kenn-abc123"
    assert handler.payload["job_id"] == "job-xyz"
    token = handler.payload["token"]
    assert automix_public_tokens.verify_job_token("job-xyz", token)
    assert handler.payload["status_path"] == f"/api/public/automix-start/status?id=job-xyz&token={token}"
    assert len(captured["files"]) == 2
    assert captured["genre"] == "edm"
    assert log and log[0][0] == "public_automix_start_upload"


def test_upload_route_missing_stem_fields_is_400(monkeypatch):
    monkeypatch.setattr(
        public_routes.stem_uploads, "parse_multipart_form",
        lambda content_type, body: {"genre": "pop"},
    )
    handler = FakeHandler(b"body", "multipart/form-data; boundary=x")

    handled = public_routes.handle_post(handler, "/api/public/automix-start", log_event=_events([]))

    assert handled is True
    assert handler.status == 400
    assert "stem_0" in handler.payload["error"]


def test_upload_route_surfaces_validation_errors(monkeypatch):
    monkeypatch.setattr(
        public_routes.stem_uploads, "parse_multipart_form",
        lambda content_type, body: {"stem_0": b"not audio", "stem_0__filename": "stem.wav"},
    )
    monkeypatch.setattr(
        automix_public, "start_public_automix",
        lambda files, **kw: {"ok": False, "error": "could not be decoded as audio"},
    )
    handler = FakeHandler(b"body", "multipart/form-data; boundary=x")

    handled = public_routes.handle_post(handler, "/api/public/automix-start", log_event=_events([]))

    assert handled is True
    assert handler.status == 400
    assert "token" not in handler.payload


def test_upload_route_is_rate_limited(monkeypatch):
    monkeypatch.setattr(
        public_routes.stem_uploads, "parse_multipart_form",
        lambda content_type, body: {"stem_0": b"RIFF", "stem_0__filename": "stem.wav"},
    )
    monkeypatch.setattr(
        automix_public, "start_public_automix",
        lambda files, **kw: {"ok": True, "project_id": "p", "job_id": "j", "status": "queued"},
    )
    max_attempts, _window = enquiry_guard.RATE_LIMITS["public_automix_start"]
    for _ in range(max_attempts):
        handler = FakeHandler(b"body", "multipart/form-data; boundary=x")
        public_routes.handle_post(handler, "/api/public/automix-start", log_event=_events([]))

    limited_handler = FakeHandler(b"body", "multipart/form-data; boundary=x")
    handled = public_routes.handle_post(limited_handler, "/api/public/automix-start", log_event=_events([]))

    assert handled is True
    assert limited_handler.status == 429


def test_status_route_requires_a_valid_token():
    handler = FakeHandler()
    query = urlencode({"id": "job-xyz", "token": "garbage"})

    handled = handle_public_get(handler, f"/api/public/automix-start/status?{query}")

    assert handled is True
    assert handler.status == 404


def test_status_route_returns_a_curated_public_view(monkeypatch):
    token = automix_public_tokens.make_job_token("job-xyz")
    monkeypatch.setattr(
        automix_jobs, "get_job_status",
        lambda job_id: {
            "id": job_id, "project_id": "kenn-abc", "status": "processing", "progress": 42,
            "genre": "edm", "error_message": "", "created_at": "t1", "updated_at": "t2",
            "result_path": "/secret/server/path/mixdown.wav", "style_prefs": '{"secret": "internal"}',
        },
    )
    handler = FakeHandler()
    query = urlencode({"id": "job-xyz", "token": token})

    handled = handle_public_get(handler, f"/api/public/automix-start/status?{query}")

    assert handled is True
    assert handler.status == 200
    assert handler.payload["status"] == "processing"
    assert handler.payload["progress"] == 42
    assert "result_path" not in handler.payload
    assert "style_prefs" not in handler.payload


def test_status_route_404s_for_unknown_job(monkeypatch):
    token = automix_public_tokens.make_job_token("job-xyz")
    monkeypatch.setattr(automix_jobs, "get_job_status", lambda job_id: None)
    handler = FakeHandler()
    query = urlencode({"id": "job-xyz", "token": token})

    handled = handle_public_get(handler, f"/api/public/automix-start/status?{query}")

    assert handled is True
    assert handler.status == 404
