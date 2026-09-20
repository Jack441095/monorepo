"""Tests for the Mix Review QA route's path handling (traversal safety)."""

from __future__ import annotations

import sys
import json
import importlib.util
from pathlib import Path
from io import BytesIO

ROOT = Path(__file__).resolve().parent.parent.parent

website_server_path = ROOT / "server" / "app" / "server.py"
spec = importlib.util.spec_from_file_location("website_server", str(website_server_path))
website_server = importlib.util.module_from_spec(spec)
sys.modules["website_server"] = website_server
spec.loader.exec_module(website_server)

if str(ROOT / "server" / "app") not in sys.path:
    sys.path.insert(0, str(ROOT / "server" / "app"))
if str(ROOT / "studio" / "audio_analysis") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))


class MockHandler(website_server.Handler):
    def __init__(self, path: str, method: str = "GET", body: bytes = b"", is_authorized: bool = True):
        self.path = path
        self.command = method
        self.headers = {
            "Content-Length": str(len(body)),
            "Content-Type": "application/json",
        }
        self.rfile = BytesIO(body)
        self.is_authorized = is_authorized
        self.status = 0
        self.payload = {}

    def content_length(self) -> int:
        return int(self.headers.get("Content-Length", "0"))

    def read_body_bytes(self) -> bytes:
        return self.rfile.read()

    def require_auth(self) -> bool:
        if self.is_authorized:
            return True
        self.send_json(401, {"error": "Dashboard password required."})
        return False

    def require_private_post(self) -> bool:
        return self.require_auth()

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload

    def read_json_body(self) -> dict:
        return json.loads(self.read_body_bytes().decode("utf-8"))


def test_mix_review_qa_defaults_to_portfolio_audio(monkeypatch, tmp_path) -> None:
    (tmp_path / "Portfolio" / "audio").mkdir(parents=True)
    monkeypatch.setattr(website_server, "BUSINESS_ROOT", tmp_path)

    handler = MockHandler("/api/admin/mix-review-qa")
    website_server.Handler.do_GET(handler)

    assert handler.status == 200
    assert handler.payload["summary"]["found"] == 0


def test_mix_review_qa_rejects_path_traversal_outside_business_root(monkeypatch, tmp_path) -> None:
    (tmp_path / "Portfolio" / "audio").mkdir(parents=True)
    secret_dir = tmp_path.parent / "definitely-outside"
    secret_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(website_server, "BUSINESS_ROOT", tmp_path)

    handler = MockHandler(f"/api/admin/mix-review-qa?path=../../../../../../../{secret_dir.name}")
    website_server.Handler.do_GET(handler)

    assert handler.status == 400
    assert "error" in handler.payload
    assert "escapes" in handler.payload["error"].lower()


def test_mix_review_qa_rejects_absolute_path_escape(monkeypatch, tmp_path) -> None:
    (tmp_path / "Portfolio" / "audio").mkdir(parents=True)
    monkeypatch.setattr(website_server, "BUSINESS_ROOT", tmp_path)

    handler = MockHandler("/api/admin/mix-review-qa?path=" + "..%2F" * 10 + "etc")
    website_server.Handler.do_GET(handler)

    assert handler.status == 400
    assert "error" in handler.payload


def test_mix_review_qa_allows_legitimate_subfolder(monkeypatch, tmp_path) -> None:
    (tmp_path / "Portfolio" / "audio" / "client1").mkdir(parents=True)
    monkeypatch.setattr(website_server, "BUSINESS_ROOT", tmp_path)

    handler = MockHandler("/api/admin/mix-review-qa?path=client1")
    website_server.Handler.do_GET(handler)

    assert handler.status == 200
    assert handler.payload["summary"]["found"] == 0


def test_mix_review_qa_unauthorized(monkeypatch, tmp_path) -> None:
    (tmp_path / "Portfolio" / "audio").mkdir(parents=True)
    monkeypatch.setattr(website_server, "BUSINESS_ROOT", tmp_path)

    handler = MockHandler("/api/admin/mix-review-qa", is_authorized=False)
    website_server.Handler.do_GET(handler)

    assert handler.status == 401
