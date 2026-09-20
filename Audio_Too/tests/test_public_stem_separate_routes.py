"""Tests for the /api/public/stem-separate POST + status/download GET routes.

Mirrors test_public_mix_doctor_route.py's pattern: monkeypatch the
stem_separation_bridge functions the routes call rather than re-exercising
the real upload/separation pipeline (that's covered by
test_stem_separation_bridge.py on its own).
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlencode

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import enquiry_guard  # noqa: E402
import public_routes  # noqa: E402
import stem_separation_bridge  # noqa: E402
import stem_separation_tokens  # noqa: E402
from app.routes.public_api_routes import handle_public_get  # noqa: E402


class FakeHandler:
    def __init__(self, body: bytes = b"", content_type: str = "", client_ip: str = "1.2.3.4") -> None:
        self._body = body
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        self.client_address = (client_ip, 12345)
        self.status = 0
        self.payload: dict = {}
        self.sent_file: tuple | None = None

    def read_body_bytes(self) -> bytes:
        return self._body

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload

    def send_file(self, path, content_type, *, filename: str = "") -> None:
        self.sent_file = (Path(path), content_type, filename)
        self.status = 200


def _events(log: list):
    def log_event(event: str, detail: str, source: str) -> None:
        log.append((event, detail, source))
    return log_event


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    yield
    for ip in ("1.2.3.4", "5.6.7.8"):
        enquiry_guard.clear_rate_limit((ip, 0), "public_stem_separate")


def test_upload_route_returns_202_with_status_link(monkeypatch):
    monkeypatch.setattr(
        public_routes.stem_uploads, "parse_multipart_form",
        lambda content_type, body: {"file": b"RIFF....WAVEfake", "file__filename": "mix.wav"},
    )
    monkeypatch.setattr(
        stem_separation_bridge, "enqueue_separation",
        lambda data, filename, **kw: {"ok": True, "job": {"id": "job-abc12345", "status": "queued"}},
    )
    handler = FakeHandler(b"fake-multipart-body", "multipart/form-data; boundary=x")
    log = []

    handled = public_routes.handle_post(handler, "/api/public/stem-separate", log_event=_events(log))

    assert handled is True
    assert handler.status == 202
    assert handler.payload["ok"] is True
    assert handler.payload["id"] == "job-abc12345"
    token = handler.payload["token"]
    assert stem_separation_tokens.verify_job_token("job-abc12345", token)
    assert handler.payload["status_path"] == f"/api/public/stem-separate/status?id=job-abc12345&token={token}"
    assert log and log[0][0] == "public_stem_separate_upload"


def test_upload_route_missing_file_field_is_400(monkeypatch):
    monkeypatch.setattr(
        public_routes.stem_uploads, "parse_multipart_form",
        lambda content_type, body: {},
    )
    handler = FakeHandler(b"body", "multipart/form-data; boundary=x")

    handled = public_routes.handle_post(handler, "/api/public/stem-separate", log_event=_events([]))

    assert handled is True
    assert handler.status == 400


def test_upload_route_surfaces_enqueue_validation_error(monkeypatch):
    monkeypatch.setattr(
        public_routes.stem_uploads, "parse_multipart_form",
        lambda content_type, body: {"file": b"not audio", "file__filename": "mix.wav"},
    )
    monkeypatch.setattr(
        stem_separation_bridge, "enqueue_separation",
        lambda data, filename, **kw: {"ok": False, "error": "could not be decoded as audio"},
    )
    handler = FakeHandler(b"body", "multipart/form-data; boundary=x")

    handled = public_routes.handle_post(handler, "/api/public/stem-separate", log_event=_events([]))

    assert handled is True
    assert handler.status == 400
    assert "token" not in handler.payload


def test_upload_route_is_rate_limited(monkeypatch):
    monkeypatch.setattr(
        public_routes.stem_uploads, "parse_multipart_form",
        lambda content_type, body: {"file": b"RIFF", "file__filename": "mix.wav"},
    )
    monkeypatch.setattr(
        stem_separation_bridge, "enqueue_separation",
        lambda data, filename, **kw: {"ok": True, "job": {"id": "job-x", "status": "queued"}},
    )
    max_attempts, _window = enquiry_guard.RATE_LIMITS["public_stem_separate"]
    for _ in range(max_attempts):
        handler = FakeHandler(b"body", "multipart/form-data; boundary=x")
        public_routes.handle_post(handler, "/api/public/stem-separate", log_event=_events([]))

    limited_handler = FakeHandler(b"body", "multipart/form-data; boundary=x")
    handled = public_routes.handle_post(limited_handler, "/api/public/stem-separate", log_event=_events([]))

    assert handled is True
    assert limited_handler.status == 429


def test_status_route_requires_a_valid_token(monkeypatch):
    handler = FakeHandler()
    query = urlencode({"id": "job-abc12345", "token": "garbage"})

    handled = handle_public_get(handler, f"/api/public/stem-separate/status?{query}")

    assert handled is True
    assert handler.status == 404


def test_status_route_returns_job_state_with_a_valid_token(monkeypatch):
    token = stem_separation_tokens.make_job_token("job-abc12345")
    monkeypatch.setattr(
        stem_separation_bridge, "job_status",
        lambda job_id: {
            "id": job_id, "status": "completed", "progress": 100, "message": "done", "error": "",
            "result": {"stems": {"drums": "/x/drums.wav", "bass": "/x/bass.wav"}},
        },
    )
    handler = FakeHandler()
    query = urlencode({"id": "job-abc12345", "token": token})

    handled = handle_public_get(handler, f"/api/public/stem-separate/status?{query}")

    assert handled is True
    assert handler.status == 200
    assert handler.payload["status"] == "completed"
    assert set(handler.payload["stems_ready"]) == {"drums", "bass"}


def test_download_route_all_serves_a_zip(monkeypatch, tmp_path):
    token = stem_separation_tokens.make_job_token("job-abc12345")
    zip_path = tmp_path / "stems.zip"
    zip_path.write_bytes(b"PK\x03\x04fake")
    monkeypatch.setattr(stem_separation_bridge, "job_zip_path", lambda job_id: zip_path)
    handler = FakeHandler()
    query = urlencode({"id": "job-abc12345", "token": token, "stem": "all"})

    handled = handle_public_get(handler, f"/api/public/stem-separate/download?{query}")

    assert handled is True
    assert handler.sent_file is not None
    assert handler.sent_file[0] == zip_path
    assert handler.sent_file[1] == "application/zip"


def test_download_route_rejects_an_unknown_stem_name(monkeypatch):
    token = stem_separation_tokens.make_job_token("job-abc12345")
    handler = FakeHandler()
    query = urlencode({"id": "job-abc12345", "token": token, "stem": "kazoo"})

    handled = handle_public_get(handler, f"/api/public/stem-separate/download?{query}")

    assert handled is True
    assert handler.status == 400


def test_download_route_404s_when_stem_not_ready(monkeypatch):
    token = stem_separation_tokens.make_job_token("job-abc12345")
    monkeypatch.setattr(stem_separation_bridge, "job_stem_path", lambda job_id, stem: None)
    handler = FakeHandler()
    query = urlencode({"id": "job-abc12345", "token": token, "stem": "drums"})

    handled = handle_public_get(handler, f"/api/public/stem-separate/download?{query}")

    assert handled is True
    assert handler.status == 404
