"""Tests for KENN server.py's /api/automix-upload + /api/automix-status --
the direct in-process bridge to business/app's automix_public.py, mirroring
test_kenn_cors.py's MockHandler pattern (call the real Handler method
directly rather than spinning up a real socket server)."""

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


def test_upload_with_no_stems_is_a_400():
    body = _multipart_body({"genre": "pop"})
    handler = MockHandler(
        headers={"Content-Type": "multipart/form-data; boundary=BOUNDARY", "Content-Length": str(len(body))},
        body=body,
    )

    server.Handler.handle_automix_upload(handler)

    assert handler.status == 400
    assert "stem_0" in handler.sent_json["error"]


def test_upload_rejects_non_multipart_content_type():
    handler = MockHandler(headers={"Content-Type": "application/json", "Content-Length": "2"}, body=b"{}")

    server.Handler.handle_automix_upload(handler)

    assert handler.status == 400


def test_upload_calls_start_public_automix_with_parsed_files(monkeypatch):
    body = _multipart_body({
        "stem_0": (b"RIFF....WAVEfake", "bass.wav"),
        "stem_1": (b"RIFF....WAVEfake2", "vocal.wav"),
        "genre": "edm",
    })
    handler = MockHandler(
        headers={"Content-Type": "multipart/form-data; boundary=BOUNDARY", "Content-Length": str(len(body))},
        body=body,
    )
    captured = {}

    def fake_start(files, **kw):
        captured["files"] = files
        captured["genre"] = kw.get("genre")
        return {"ok": True, "project_id": "kenn-abc", "job_id": "job-1", "status": "queued"}

    monkeypatch.setattr(server, "automix_public", type("M", (), {"start_public_automix": staticmethod(fake_start)}))

    server.Handler.handle_automix_upload(handler)

    assert handler.status == 200
    assert handler.sent_json["job_id"] == "job-1"
    assert len(captured["files"]) == 2
    assert captured["genre"] == "edm"


def test_upload_503s_when_automix_is_unavailable(monkeypatch):
    monkeypatch.setattr(server, "automix_public", None)
    handler = MockHandler(headers={"Content-Type": "multipart/form-data; boundary=BOUNDARY"})

    server.Handler.handle_automix_upload(handler)

    assert handler.status == 503


def test_status_route_returns_curated_fields(monkeypatch):
    monkeypatch.setattr(
        server, "automix_jobs",
        type("M", (), {"get_job_status": staticmethod(lambda job_id: {
            "id": job_id, "project_id": "kenn-abc", "status": "processing", "progress": 55,
            "genre": "pop", "error_message": "", "result_path": "/secret/path.wav",
        })}),
    )
    handler = MockHandler()
    from urllib.parse import urlparse
    parsed = urlparse("/api/automix-status?id=job-1")

    # do_GET dispatches by path -- call the relevant branch logic directly
    # via do_GET itself, since that's the real entrypoint this route lives behind.
    handler.path = "/api/automix-status?id=job-1"
    server.Handler.do_GET(handler)

    assert handler.status == 200
    assert handler.sent_json["status"] == "processing"
    assert "result_path" not in handler.sent_json


def test_status_route_requires_a_job_id():
    handler = MockHandler()
    handler.path = "/api/automix-status"

    server.Handler.do_GET(handler)

    assert handler.status == 400


def test_status_route_404s_for_unknown_job(monkeypatch):
    monkeypatch.setattr(
        server, "automix_jobs",
        type("M", (), {"get_job_status": staticmethod(lambda job_id: None)}),
    )
    handler = MockHandler()
    handler.path = "/api/automix-status?id=nope"

    server.Handler.do_GET(handler)

    assert handler.status == 404


def test_download_route_serves_the_mixdown_wav(monkeypatch):
    monkeypatch.setattr(
        server, "automix_public",
        type("M", (), {"delivery_wav_bytes": staticmethod(lambda job_id: (b"RIFF-fake-wav", "mixdown_v1.wav"))}),
    )
    handler = MockHandler()
    handler.path = "/api/automix-download?id=job-1&kind=wav"

    server.Handler.do_GET(handler)

    assert handler.status == 200
    assert handler.sent_bytes[0] == b"RIFF-fake-wav"
    assert handler.sent_bytes[1] == "audio/wav"
    assert handler.sent_bytes[2] == "mixdown_v1.wav"


def test_download_route_serves_the_zip(monkeypatch, tmp_path):
    zip_path = tmp_path / "delivery.zip"
    zip_path.write_bytes(b"PK\x03\x04fake")
    monkeypatch.setattr(
        server, "automix_public",
        type("M", (), {"delivery_zip_path": staticmethod(lambda job_id: zip_path)}),
    )
    handler = MockHandler()
    handler.path = "/api/automix-download?id=job-1&kind=zip"

    server.Handler.do_GET(handler)

    assert handler.status == 200
    assert handler.sent_bytes[1] == "application/zip"


def test_download_route_404s_when_wav_not_ready(monkeypatch):
    monkeypatch.setattr(
        server, "automix_public",
        type("M", (), {"delivery_wav_bytes": staticmethod(lambda job_id: None)}),
    )
    handler = MockHandler()
    handler.path = "/api/automix-download?id=job-1"

    server.Handler.do_GET(handler)

    assert handler.status == 404


def test_download_route_requires_a_job_id():
    handler = MockHandler()
    handler.path = "/api/automix-download"

    server.Handler.do_GET(handler)

    assert handler.status == 400


def test_download_route_503s_when_unavailable(monkeypatch):
    monkeypatch.setattr(server, "automix_public", None)
    handler = MockHandler()
    handler.path = "/api/automix-download?id=job-1"

    server.Handler.do_GET(handler)

    assert handler.status == 503
