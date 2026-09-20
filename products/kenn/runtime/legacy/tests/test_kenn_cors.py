"""CORS boundary tests for the standalone KENN service."""

from __future__ import annotations

import io

from kenn import server


class MockHandler(server.Handler):
    def __init__(self, origin: str):
        self.headers = {"Origin": origin}
        self.status = 0
        self.sent_headers: list[tuple[str, str]] = []
        self.wfile = io.BytesIO()

    def send_response(self, status: int, message=None) -> None:
        self.status = status

    def send_header(self, name: str, value: str) -> None:
        self.sent_headers.append((name, value))

    def end_headers(self) -> None:
        return


def test_cors_allows_only_configured_local_dashboard_origin() -> None:
    handler = MockHandler("http://127.0.0.1:8080")

    server.Handler.do_OPTIONS(handler)

    assert handler.status == 204
    assert ("Access-Control-Allow-Origin", "http://127.0.0.1:8080") in handler.sent_headers
    assert not any(value == "*" for _, value in handler.sent_headers)


def test_cors_rejects_unknown_origin() -> None:
    handler = MockHandler("https://attacker.example")

    server.Handler.do_OPTIONS(handler)

    assert handler.status == 403
    assert b"Cross-origin request rejected" in handler.wfile.getvalue()
    assert not any(name == "Access-Control-Allow-Origin" for name, _ in handler.sent_headers)


def test_cors_allows_kenn_same_origin() -> None:
    handler = MockHandler("http://127.0.0.1:8090")
    server.Handler.do_OPTIONS(handler)
    assert handler.status == 204


def test_actual_post_rejects_unknown_origin_not_only_preflight() -> None:
    handler = MockHandler("https://attacker.example")
    handler.path = "/api/session/clear"
    server.Handler.do_POST(handler)
    assert handler.status == 403
    assert b"Cross-origin request rejected" in handler.wfile.getvalue()


def test_kenn_server_errors_hide_internal_details() -> None:
    payload = server.safe_error_payload(500, {"error": "secret path /tmp/client.wav"}, "kenn123")
    assert payload == {
        "error": "The request could not be completed.",
        "error_code": "internal_error",
        "retryable": False,
        "error_id": "kenn123",
    }
