"""Tests for the Listening Benchmark API (business/app/routes/benchmark_routes.py).

Previously this route returned a hardcoded, always-identical fake session
(project_id "lbv1_001", audio URLs that 404 -- business/data/mix_outputs was
always empty) and stored ratings via a raw sqlite3 connection with a path
computed one directory short of the repo root, silently writing every
submitted rating into an orphaned database file
(business/data/audio_too.db) that nothing else in the app ever reads --
functionally indistinguishable from data loss. These tests exercise the
real fix: a randomly-selected real package, real audio bytes served back,
and ratings written through the shared db module.
"""

from __future__ import annotations

import json
import sys
import importlib.util
import wave
from io import BytesIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

website_server_path = ROOT / "server" / "app" / "server.py"
spec = importlib.util.spec_from_file_location("website_server_benchmark", str(website_server_path))
website_server = importlib.util.module_from_spec(spec)
sys.modules["website_server_benchmark"] = website_server
if str(ROOT / "server" / "app") not in sys.path:
    sys.path.insert(0, str(ROOT / "server" / "app"))
if str(ROOT / "studio" / "audio_analysis") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))
spec.loader.exec_module(website_server)

import db  # noqa: E402
from app.routes import benchmark_routes  # noqa: E402


class MockHandler(website_server.Handler):
    def __init__(self, path: str, method: str = "GET", body: bytes = b"", is_authorized: bool = True):
        self.path = path
        self.command = method
        self.headers = {"Content-Length": str(len(body)), "Content-Type": "application/json"}
        self.rfile = BytesIO(body)
        self.is_authorized = is_authorized
        self.status = 0
        self.payload = {}
        self.response_bytes = b""
        self.content_type = ""
        self.filename = ""

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

    def send_bytes(self, status: int, body: bytes, content_type: str, *, filename: str = "") -> None:
        self.status = status
        self.response_bytes = body
        self.content_type = content_type
        self.filename = filename

    def send_file(self, path: Path, content_type: str, *, filename: str = "") -> None:
        self.send_bytes(200, path.read_bytes(), content_type, filename=filename)


def _wav_bytes(tone: int) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(bytes([tone, 0]) * 80)
    return buf.getvalue()


@pytest.fixture
def setup_db(monkeypatch, tmp_path):
    db_file = tmp_path / "audio_too.db"
    monkeypatch.setattr(db, "DB_PATH", db_file)
    monkeypatch.setattr(db, "_migration_done", False)
    db.init_db()
    return tmp_path


@pytest.fixture
def fake_packages(monkeypatch, tmp_path):
    """One real-shaped package: A.wav/B.wav + a public listener_manifest.json.
    private_lineage.json is deliberately NOT created here -- the route must
    never need it."""
    packages_root = tmp_path / "packages"
    pkg_dir = packages_root / "lbv1-test"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "A.wav").write_bytes(_wav_bytes(10))
    (pkg_dir / "B.wav").write_bytes(_wav_bytes(20))
    (pkg_dir / "listener_manifest.json").write_text(
        json.dumps({"project_id": "lbv1-test", "duration_seconds": 2.0, "schema": "audio-too.automix-listening-package/v1"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(benchmark_routes, "BENCHMARK_PACKAGES_ROOT", packages_root)
    return packages_root


def test_session_returns_a_real_package_not_the_old_hardcoded_one(fake_packages) -> None:
    handler = MockHandler("/api/benchmark/session")
    handled = benchmark_routes.handle_benchmark_get(handler, "/api/benchmark/session")

    assert handled is True
    assert handler.status == 200
    assert handler.payload["ok"] is True
    assert handler.payload["project_id"] == "lbv1-test"
    assert handler.payload["mix1_url"] == "/api/benchmark/audio/lbv1-test/1"
    assert handler.payload["mix2_url"] == "/api/benchmark/audio/lbv1-test/2"
    assert handler.payload["duration_seconds"] == 2.0
    # The old bug: every session was this exact literal, regardless of what
    # (if anything) actually existed on disk.
    assert handler.payload["project_id"] != "lbv1_001"


def test_session_404s_honestly_when_no_packages_exist(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(benchmark_routes, "BENCHMARK_PACKAGES_ROOT", tmp_path / "does-not-exist")
    handler = MockHandler("/api/benchmark/session")

    handled = benchmark_routes.handle_benchmark_get(handler, "/api/benchmark/session")

    assert handled is True
    assert handler.status == 404
    assert handler.payload["ok"] is False


def test_audio_route_serves_the_real_wav_bytes(fake_packages) -> None:
    handler = MockHandler("/api/benchmark/audio/lbv1-test/1")
    handled = benchmark_routes.handle_benchmark_get(handler, "/api/benchmark/audio/lbv1-test/1")

    assert handled is True
    assert handler.status == 200
    assert handler.content_type == "audio/wav"
    assert handler.response_bytes == (fake_packages / "lbv1-test" / "A.wav").read_bytes()


def test_audio_route_404s_for_unknown_package(fake_packages) -> None:
    handler = MockHandler("/api/benchmark/audio/no-such-package/1")
    handled = benchmark_routes.handle_benchmark_get(handler, "/api/benchmark/audio/no-such-package/1")

    assert handled is True
    assert handler.status == 404


def test_audio_route_rejects_path_traversal(fake_packages) -> None:
    handler = MockHandler("/api/benchmark/audio/../1")
    handled = benchmark_routes.handle_benchmark_get(handler, "/api/benchmark/audio/../1")

    assert handled is True
    assert handler.status == 400


def test_rate_requires_authentication(setup_db) -> None:
    payload = {"session_id": "s1", "project_id": "lbv1-test", "preference": "mix1"}
    handler = MockHandler(
        "/api/benchmark/rate", method="POST", body=json.dumps(payload).encode("utf-8"), is_authorized=False,
    )

    handled = benchmark_routes.handle_benchmark_post(handler, "/api/benchmark/rate")

    assert handled is True
    assert handler.status == 401


def test_rate_writes_through_the_shared_db_not_an_orphaned_connection(setup_db) -> None:
    payload = {
        "session_id": "sess_abc",
        "project_id": "lbv1-test",
        "active_mix_evaluated": 2,
        "clarity": 5,
        "bass": 4,
        "width": 5,
        "punch": 4,
        "preference": "mix2",
        "producer_name": "Real Producer",
        "feedback_text": "Cleaner low end on B.",
    }
    handler = MockHandler("/api/benchmark/rate", method="POST", body=json.dumps(payload).encode("utf-8"))

    handled = benchmark_routes.handle_benchmark_post(handler, "/api/benchmark/rate")

    assert handled is True
    assert handler.status == 200
    assert handler.payload["ok"] is True
    assert handler.payload["session_id"] == "sess_abc"

    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM listening_benchmark_ratings WHERE session_id = ?", ("sess_abc",)
        ).fetchone()
    assert row is not None
    assert row["package_id"] == "lbv1-test"
    assert row["preference"] == "mix2"
    assert row["producer_name"] == "Real Producer"
    assert row["score_clarity"] == 5
    assert row["active_mix_evaluated"] == 2


def test_rate_rejects_missing_required_fields(setup_db) -> None:
    handler = MockHandler("/api/benchmark/rate", method="POST", body=json.dumps({}).encode("utf-8"))

    handled = benchmark_routes.handle_benchmark_post(handler, "/api/benchmark/rate")

    assert handled is True
    assert handler.status == 400
