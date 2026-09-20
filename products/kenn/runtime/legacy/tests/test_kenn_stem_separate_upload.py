"""Tests for KENN server.py's /api/stem-separate-upload + status + download
-- direct in-process bridge to business/app's stem_separation_bridge.py,
mirroring test_kenn_automix_upload.py's MockHandler pattern."""

from __future__ import annotations

import io

from kenn import server


class MockHandler(server.Handler):
    def __init__(self, *, headers: dict | None = None, body: bytes = b""):
        self.headers = headers or {}
        self.client_address = ("127.0.0.1", 0)
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.status = 0
        self.sent_json: dict = {}
        self.sent_bytes: tuple | None = None

    def send_response(self, status: int, message=None) -> None:
        self.status = status

    def send_header(self, name: str, value: str) -> None:
        pass

    def end_headers(self) -> None:
        pass

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.sent_json = payload

    def send_bytes(self, status: int, body: bytes, content_type: str, *, filename: str = "") -> None:
        self.status = status
        self.sent_bytes = (body, content_type, filename)

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


def test_upload_calls_enqueue_separation(monkeypatch):
    body = _multipart_body({"file": (b"RIFF....WAVEfake", "mix.wav")})
    handler = MockHandler(
        headers={"Content-Type": "multipart/form-data; boundary=BOUNDARY", "Content-Length": str(len(body))},
        body=body,
    )
    captured = {}

    def fake_enqueue(file_bytes, filename, **kw):
        captured["file_bytes"] = file_bytes
        captured["filename"] = filename
        return {"ok": True, "job": {"id": "job-1", "status": "queued"}}

    monkeypatch.setattr(
        server, "stem_separation_bridge",
        type("M", (), {"enqueue_separation": staticmethod(fake_enqueue)}),
    )

    server.Handler.handle_stem_separate_upload(handler)

    assert handler.status == 200
    assert handler.sent_json["job_id"] == "job-1"
    assert captured["filename"] == "mix.wav"
    assert captured["file_bytes"] == b"RIFF....WAVEfake"


def test_upload_missing_file_field_is_400():
    body = _multipart_body({"other": "x"})
    handler = MockHandler(
        headers={"Content-Type": "multipart/form-data; boundary=BOUNDARY", "Content-Length": str(len(body))},
        body=body,
    )

    server.Handler.handle_stem_separate_upload(handler)

    assert handler.status == 400


def test_upload_surfaces_validation_errors(monkeypatch):
    body = _multipart_body({"file": (b"not audio", "mix.wav")})
    handler = MockHandler(
        headers={"Content-Type": "multipart/form-data; boundary=BOUNDARY", "Content-Length": str(len(body))},
        body=body,
    )
    monkeypatch.setattr(
        server, "stem_separation_bridge",
        type("M", (), {"enqueue_separation": staticmethod(
            lambda file_bytes, filename, **kw: {"ok": False, "error": "could not be decoded"}
        )}),
    )

    server.Handler.handle_stem_separate_upload(handler)

    assert handler.status == 400


def test_upload_503s_when_unavailable(monkeypatch):
    monkeypatch.setattr(server, "stem_separation_bridge", None)
    handler = MockHandler(headers={"Content-Type": "multipart/form-data; boundary=BOUNDARY"})

    server.Handler.handle_stem_separate_upload(handler)

    assert handler.status == 503


def test_status_route_returns_stems_ready(monkeypatch):
    monkeypatch.setattr(
        server, "stem_separation_bridge",
        type("M", (), {"job_status": staticmethod(lambda job_id: {
            "id": job_id, "status": "completed", "progress": 100, "message": "done", "error": "",
            "result": {"stems": {"drums": "/x/drums.wav", "bass": "/x/bass.wav"}},
        })}),
    )
    handler = MockHandler()
    handler.path = "/api/stem-separate-status?id=job-1"

    server.Handler.do_GET(handler)

    assert handler.status == 200
    assert set(handler.sent_json["stems_ready"]) == {"drums", "bass"}


def test_status_route_404s_for_unknown_job(monkeypatch):
    monkeypatch.setattr(
        server, "stem_separation_bridge",
        type("M", (), {"job_status": staticmethod(lambda job_id: None)}),
    )
    handler = MockHandler()
    handler.path = "/api/stem-separate-status?id=nope"

    server.Handler.do_GET(handler)

    assert handler.status == 404


def test_download_route_serves_a_stem(monkeypatch, tmp_path):
    stem_path = tmp_path / "drums.wav"
    stem_path.write_bytes(b"RIFF-fake-drums")
    monkeypatch.setattr(
        server, "stem_separation_bridge",
        type("M", (), {
            "job_stem_path": staticmethod(lambda job_id, stem: stem_path),
            "STEM_NAMES": ("drums", "bass", "vocals", "other"),
        }),
    )
    handler = MockHandler()
    handler.path = "/api/stem-separate-download?id=job-1&stem=drums"

    server.Handler.do_GET(handler)

    assert handler.status == 200
    assert handler.sent_bytes[0] == b"RIFF-fake-drums"
    assert handler.sent_bytes[1] == "audio/wav"


def test_download_route_serves_a_zip_for_all(monkeypatch, tmp_path):
    zip_path = tmp_path / "stems.zip"
    zip_path.write_bytes(b"PK\x03\x04fake")
    monkeypatch.setattr(
        server, "stem_separation_bridge",
        type("M", (), {"job_zip_path": staticmethod(lambda job_id: zip_path)}),
    )
    handler = MockHandler()
    handler.path = "/api/stem-separate-download?id=job-1&stem=all"

    server.Handler.do_GET(handler)

    assert handler.status == 200
    assert handler.sent_bytes[1] == "application/zip"


def test_download_route_404s_when_not_ready(monkeypatch):
    monkeypatch.setattr(
        server, "stem_separation_bridge",
        type("M", (), {"job_stem_path": staticmethod(lambda job_id, stem: None), "STEM_NAMES": ("drums", "bass", "vocals", "other")}),
    )
    handler = MockHandler()
    handler.path = "/api/stem-separate-download?id=job-1&stem=drums"

    server.Handler.do_GET(handler)

    assert handler.status == 404
