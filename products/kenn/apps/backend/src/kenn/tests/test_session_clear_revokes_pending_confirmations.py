"""Clearing a chat used to leave its Apply token live for the rest of the five minute window."""

from collections import defaultdict, deque
import json
from threading import Thread
import urllib.request

from fastapi.testclient import TestClient
import pytest

import kenn.server_rate_limit as rate_limit
from kenn.core import answer_upgrades, confirmation


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch):
    monkeypatch.setattr(confirmation, "_USED_TOKENS", set())
    monkeypatch.setattr(confirmation, "_ISSUED_TOKENS", {})
    monkeypatch.setattr(confirmation, "_REVOKED_TOKENS", set())
    monkeypatch.setattr(answer_upgrades, "_RESULTS", {})
    monkeypatch.setattr(answer_upgrades, "_TURNS", {})
    monkeypatch.setattr(rate_limit, "RATE_BUCKETS", defaultdict(deque))


@pytest.fixture(params=["http", "fastapi"])
def post(request):
    from kenn import server
    from kenn.routes.fastapi_app import app

    if request.param == "fastapi":
        with TestClient(app) as client:
            yield lambda path, payload: client.post(path, json=payload).status_code
        return

    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True).start()

    def send(path, payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{httpd.server_port}{path}",
            data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status

    try:
        yield send
    finally:
        httpd.shutdown()
        httpd.server_close()


def _issue(session_id):
    binding = {"session_id": session_id, "service_id": "ableton_action", "text": "set_volume"}
    token, _ = confirmation.issue_confirmation(**binding)
    return token, binding


def test_clearing_a_session_revokes_its_pending_apply_token(post):
    token, binding = _issue("song-a")
    assert confirmation.pending_confirmation_count(session_id="song-a") == 1
    assert post("/api/session/clear", {"id": "song-a"}) == 200
    assert confirmation.pending_confirmation_count(session_id="song-a") == 0
    assert not confirmation.consume_confirmation(token, **binding)


def test_clearing_one_session_leaves_another_sessions_token_alone(post):
    _issue("song-a")
    other, binding = _issue("song-b")
    assert post("/api/session/clear", {"id": "song-a"}) == 200
    assert confirmation.pending_confirmation_count(session_id="song-b") == 1
    assert confirmation.consume_confirmation(other, **binding)
