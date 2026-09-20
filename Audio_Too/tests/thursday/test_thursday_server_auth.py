"""Auth for the standalone Thursday HTTP server (thursday/server.py, port 8092).

Regression guard for the fail-closed token: there must be NO publicly-known default
token, unconfigured production must deny every request, and the server must refuse
to start without a token outside dev mode.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
import io

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thursday import server as ts  # noqa: E402


def _handler(headers: dict) -> SimpleNamespace:
    return SimpleNamespace(headers=headers)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    for key in ("THURSDAY_SERVER_TOKEN", "AUDIO_TOO_DASHBOARD_PASSWORD", "AUDIO_TOO_DEV"):
        monkeypatch.delenv(key, raising=False)
    yield


def test_no_publicly_known_default_token_outside_dev():
    # Nothing configured, not dev → token is empty (fail closed), never "thursday".
    assert ts._server_token() == ""


def test_dev_mode_allows_local_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUDIO_TOO_DEV", "1")
    assert ts._server_token() == "thursday-dev"


def test_change_me_placeholder_is_treated_as_unconfigured():
    # The .env.example placeholder must not become a usable token in production.
    import os
    os.environ["AUDIO_TOO_DASHBOARD_PASSWORD"] = "change-me"
    try:
        assert ts._server_token() == ""
    finally:
        del os.environ["AUDIO_TOO_DASHBOARD_PASSWORD"]


def test_configured_token_is_honoured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("THURSDAY_SERVER_TOKEN", "s3cret-token")
    assert ts._server_token() == "s3cret-token"


def test_unauthorised_when_unconfigured():
    # No token configured → every request denied, even with a header present.
    assert ts._is_authorised(_handler({"X-Thursday-Token": "thursday"})) is False
    assert ts._is_authorised(_handler({"Authorization": "Bearer thursday"})) is False


def test_authorised_with_correct_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("THURSDAY_SERVER_TOKEN", "s3cret-token")
    assert ts._is_authorised(_handler({"X-Thursday-Token": "s3cret-token"})) is True
    assert ts._is_authorised(_handler({"Authorization": "Bearer s3cret-token"})) is True


def test_rejects_wrong_and_missing_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("THURSDAY_SERVER_TOKEN", "s3cret-token")
    assert ts._is_authorised(_handler({"X-Thursday-Token": "wrong"})) is False
    assert ts._is_authorised(_handler({})) is False


def test_start_refuses_without_token_outside_dev():
    with pytest.raises(SystemExit):
        ts._require_token_or_exit()


def test_start_allowed_in_dev(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUDIO_TOO_DEV", "1")
    ts._require_token_or_exit()  # should not raise


def test_cors_origin_is_scoped_not_wildcard():
    assert ts._cors_origin() == "http://127.0.0.1:8080"
    assert ts._cors_origin() != "*"


def test_legacy_ask_endpoint_delegates_to_canonical_bridge(monkeypatch):
    sent = {}

    class FakeHandler:
        def _send_error(self, status, message):
            sent.update({"status": status, "error": message})

        def _send_json(self, status, payload):
            sent.update({"status": status, "payload": payload})

    monkeypatch.setattr(
        "thursday.bridge.ask",
        lambda question, session_id="": {
            "answer": f"canonical: {question}",
            "session_id": session_id,
            "status": "succeeded",
            "envelope": {"schema_version": 1},
        },
    )

    ts.Handler._handle_ask(FakeHandler(), {"question": "status", "session_id": "s-1"})

    assert sent["status"] == 200
    assert sent["payload"]["ok"] is True
    assert sent["payload"]["answer"] == "canonical: status"
    assert sent["payload"]["envelope"]["schema_version"] == 1


def test_request_body_limit_rejects_oversized_json() -> None:
    sent = {}

    class FakeHandler:
        headers = {"Content-Length": str(ts.MAX_REQUEST_BODY_BYTES + 1)}
        rfile = io.BytesIO(b"")

        def _send_error(self, status, message, code=""):
            sent.update({"status": status, "message": message, "code": code})

    assert ts.Handler._read_json(FakeHandler()) is None
    assert sent["status"] == 413


def test_command_rate_limit_is_bounded() -> None:
    ts._rate_buckets.clear()
    outcomes = [ts._rate_allowed("test-client", "/command")[0] for _ in range(31)]
    assert outcomes[:30] == [True] * 30
    assert outcomes[30] is False
    ts._rate_buckets.clear()
