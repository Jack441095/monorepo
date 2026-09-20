"""Tests for the Mix Targets GET and POST API endpoints."""

from __future__ import annotations

import sys
import json
import importlib.util
from pathlib import Path
from io import BytesIO

ROOT = Path(__file__).resolve().parent.parent.parent

# Dynamically import app's server.py to avoid namespace collisions with KENN's server.py
website_server_path = ROOT / "server" / "app" / "server.py"
spec = importlib.util.spec_from_file_location("website_server", str(website_server_path))
website_server = importlib.util.module_from_spec(spec)
sys.modules["website_server"] = website_server
spec.loader.exec_module(website_server)

# Ensure Website directory is in sys.path for internal relative imports inside website_server
if str(ROOT / "server" / "app") not in sys.path:
    sys.path.insert(0, str(ROOT / "server" / "app"))
if str(ROOT / "studio" / "audio_analysis") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

from audio_analysis.mix_review import mix_review


class MockHandler(website_server.Handler):
    def __init__(self, path: str, method: str = "GET", body: bytes = b"", is_authorized: bool = True):
        self.path = path
        self.command = method
        self.headers = {
            "Content-Length": str(len(body)),
            "Content-Type": "application/json"
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


def test_get_mix_targets_unauthorized(monkeypatch) -> None:
    handler = MockHandler("/api/admin/mix-targets", is_authorized=False)
    website_server.Handler.do_GET(handler)
    assert handler.status == 401
    assert "error" in handler.payload


def test_get_mix_targets_authorized(monkeypatch, tmp_path) -> None:
    temp_config = tmp_path / "mix_review_targets.json"
    monkeypatch.setattr(mix_review, "TARGET_CONFIG_PATH", temp_config)
    
    goals = {
        "premaster": {
            "summary": "Premaster target.",
            "checks": [
                {"label": "Peak headroom", "metric": "peak_dbfs", "max": -1.0, "target": "Peak at or below -1 dBFS", "education": "Premasters need space."}
            ]
        }
    }
    mix_review.save_mix_review_targets(goals)
    
    handler = MockHandler("/api/admin/mix-targets", is_authorized=True)
    website_server.Handler.do_GET(handler)
    
    assert handler.status == 200
    assert handler.payload["goals"]["premaster"]["summary"] == "Premaster target."
    assert handler.payload["goals"]["premaster"]["checks"][0]["label"] == "Peak headroom"


def test_post_mix_targets_unauthorized(monkeypatch) -> None:
    handler = MockHandler("/api/admin/mix-targets", method="POST", body=b"{}", is_authorized=False)
    website_server.Handler.do_POST(handler)
    assert handler.status == 401
    assert "error" in handler.payload


def test_post_mix_targets_authorized(monkeypatch, tmp_path) -> None:
    temp_config = tmp_path / "mix_review_targets.json"
    monkeypatch.setattr(mix_review, "TARGET_CONFIG_PATH", temp_config)
    
    events = []
    monkeypatch.setattr(website_server, "log_event", lambda kind, detail, actor: events.append((kind, detail, actor)))
    
    payload = {
        "goals": {
            "club": {
                "summary": "Custom club summary.",
                "checks": [
                    {"label": "Club low-end weight", "path": "tonal_balance.low_end_share", "min": 0.2, "max": 0.6, "target": "Around 20-60%", "education": "Controlled low end"}
                ]
            }
        }
    }
    body = json.dumps(payload).encode("utf-8")
    handler = MockHandler("/api/admin/mix-targets", method="POST", body=body, is_authorized=True)
    
    website_server.Handler.do_POST(handler)
    
    assert handler.status == 200
    assert handler.payload["ok"] is True
    
    saved_targets = mix_review.get_mix_review_targets()
    assert saved_targets["goals"]["club"]["summary"] == "Custom club summary."
    assert saved_targets["goals"]["club"]["checks"][0]["path"] == ["tonal_balance", "low_end_share"]
    
    assert len(events) == 1
    assert events[0][0] == "mix_targets_updated"
    assert events[0][2] == "dashboard"
