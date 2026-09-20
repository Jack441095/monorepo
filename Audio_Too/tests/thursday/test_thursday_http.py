from __future__ import annotations

import importlib.util
import http.cookiejar
import json
import sys
import threading
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import pytest

from nite_core import AssistantResponse, ResultEnvelope


ROOT = Path(__file__).resolve().parent.parent.parent
WEBSITE_ROOT = ROOT / "server" / "app"


def _load_website_server():
    if str(WEBSITE_ROOT) not in sys.path:
        sys.path.insert(0, str(WEBSITE_ROOT))
    spec = importlib.util.spec_from_file_location("thursday_http_website_server", WEBSITE_ROOT / "server.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def website_server():
    return _load_website_server()


def _post_json(
    url: str,
    payload: dict,
    *,
    opener: urllib.request.OpenerDirector | None = None,
    csrf_token: str = "",
) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    client = opener or urllib.request.build_opener()
    with client.open(request, timeout=10) as response:
        return response.status, json.load(response)


def test_thursday_http_api_preserves_context_across_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, website_server
) -> None:
    from thursday import monitor, session_manager
    from thursday import client as thursday_client

    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / "current")
    monkeypatch.setattr(monitor, "ALERTS_DIR", tmp_path / "alerts")
    monkeypatch.setattr(thursday_client, "client_summary", lambda _records, name, **kwargs: f"Client: {name}")
    monkeypatch.setenv("AUDIO_TOO_DASHBOARD_PASSWORD", "thursday-http-test-secret")
    monkeypatch.setenv("AUDIO_TOO_SESSION_SECRET", "thursday-http-session-secret")

    server = HTTPServer(("127.0.0.1", 0), website_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    endpoint = f"{base_url}/api/thursday/ask"
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    try:
        login_status, login = _post_json(
            f"{base_url}/api/auth/login",
            {"password": "thursday-http-test-secret"},
            opener=opener,
        )
        assert login_status == 200
        assert login["authenticated"] is True
        first_status, first = _post_json(
            endpoint,
            {"question": "tell me about Jordan", "session_id": ""},
            opener=opener,
            csrf_token=login["csrf_token"],
        )
        second_status, second = _post_json(
            endpoint,
            {"question": "who is her", "session_id": first["session_id"]},
            opener=opener,
            csrf_token=login["csrf_token"],
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert first_status == second_status == 200
    assert first["service"] == second["service"] == "client_info"
    assert second["session_id"] == first["session_id"]
    assert second["intent"] == "client_mgmt"
    assert second["navigate_url"] == "/dashboard?tab=crm"
    assert second["schema_version"] == 1
    assert second["status"] == "succeeded"
    assert second["request_id"] != second["correlation_id"]
    assert len(second["correlation_id"]) == 12
    envelope = ResultEnvelope.from_dict(second["envelope"])
    assistant = AssistantResponse.from_dict(
        {key: value for key, value in envelope.result.items() if key != "capability"}
    )
    assert assistant.session_id == second["session_id"]
    assert assistant.intent == "client_mgmt"
    assert assistant.service == "client_info"
    assert assistant.suggestions == tuple(second["suggestions"])
    stored = session_manager.load_session(first["session_id"])
    assert stored is not None
    assert stored["context"]["current_client"] == "Jordan"
    assert [turn["role"] for turn in stored["turns"]] == ["user", "thursday", "user", "thursday"]


@pytest.mark.parametrize("relative_path", ["server/app/static/thursday.html", "server/app/static/hub.html"])
def test_thursday_ui_posts_and_reuses_session_id(relative_path: str) -> None:
    html = (ROOT / relative_path).read_text(encoding="utf-8")
    assert "/api/thursday/ask" in html
    assert "session_id" in html
    assert "data.session_id" in html or "d.session_id" in html
    assert "Content-Type': 'application/json" in html or "Content-Type':'application/json" in html
    assert "escapeHtml" in html or "function esc" in html


def test_hub_allows_same_origin_microphone(website_server) -> None:
    server = HTTPServer(("127.0.0.1", 0), website_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_port}/hub", timeout=5
        ) as response:
            assert response.headers["Permissions-Policy"] == (
                "camera=(), microphone=(self), geolocation=()"
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_production_server_uses_threaded_http(website_server) -> None:
    from http.server import ThreadingHTTPServer

    assert website_server.ThreadingHTTPServer is ThreadingHTTPServer


def test_static_manifest_supports_head_requests(website_server) -> None:
    server = HTTPServer(("127.0.0.1", 0), website_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/manifest.webmanifest",
            method="HEAD",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200
            assert response.headers["Content-Type"] == "application/manifest+json"
            assert response.read() == b""
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_browser_audio_uses_local_transcription_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, website_server
) -> None:
    from thursday import voice

    monkeypatch.setenv("AUDIO_TOO_DASHBOARD_PASSWORD", "voice-http-test-secret")
    monkeypatch.setenv("AUDIO_TOO_SESSION_SECRET", "voice-http-session-secret")
    monkeypatch.setattr(
        voice,
        "transcribe_with_metadata",
        lambda path: {
            "text": "speak with KENN" if Path(path).read_bytes() == b"browser-audio" else "",
            "confidence": 1.0,
            "no_speech_prob": 0.0,
            "language": "en",
            "duration": 1.0,
            "clipping": False,
            "noise_floor_db": -60.0,
        },
    )
    server = HTTPServer(("127.0.0.1", 0), website_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    try:
        _, login = _post_json(
            f"{base_url}/api/auth/login",
            {"password": "voice-http-test-secret"},
            opener=opener,
        )
        request = urllib.request.Request(
            f"{base_url}/api/thursday/transcribe",
            data=b"browser-audio",
            method="POST",
            headers={
                "Content-Type": "audio/webm;codecs=opus",
                "X-CSRF-Token": login["csrf_token"],
            },
        )
        with opener.open(request, timeout=10) as response:
            status, result = response.status, json.load(response)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 200
    assert result == {
        "ok": True,
        "text": "speak with KENN",
        "engine": "local-whisper",
        "confidence": 1.0,
        "no_speech_prob": 0.0,
        "language": "en",
        "duration": 1.0,
        "clipping": False,
        "noise_floor_db": -60.0,
    }
