"""Network-boundary tests for KENN web ingestion."""

from __future__ import annotations

import socket
from email.message import Message

import pytest

from kenn.retrieval import web_ingest


def resolved(ip: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost/admin",
        "http://127.0.0.1:8080/private",
        "http://169.254.169.254/latest/meta-data",
        "https://user:password@example.com/",
        "https://example.com:8443/",
    ],
)
def test_validate_public_url_rejects_unsafe_targets(monkeypatch, url: str) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: resolved("127.0.0.1"))
    with pytest.raises(ValueError):
        web_ingest.validate_public_url(url)


def test_validate_public_url_accepts_globally_routable_target(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: resolved("93.184.216.34"))
    assert web_ingest.validate_public_url("https://example.com/article") == "https://example.com/article"


def test_redirect_handler_revalidates_destination(monkeypatch) -> None:
    checked = []
    monkeypatch.setattr(web_ingest, "validate_public_url", checked.append)
    handler = web_ingest.PublicOnlyRedirectHandler()
    request = type("Request", (), {})()
    monkeypatch.setattr(
        web_ingest.urlrequest.HTTPRedirectHandler,
        "redirect_request",
        lambda *_args: "redirected",
    )

    assert handler.redirect_request(request, None, 302, "Found", {}, "https://example.com/next") == "redirected"
    assert checked == ["https://example.com/next"]


class FakeResponse:
    def __init__(self, body: bytes, content_type: str, content_length: str = ""):
        self.body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        if content_length:
            self.headers["Content-Length"] = content_length

    def read(self, limit: int) -> bytes:
        return self.body[:limit]


def test_html_response_enforces_type_and_size() -> None:
    with pytest.raises(ValueError, match="HTML"):
        web_ingest.read_html_response(FakeResponse(b"{}", "application/json"))
    with pytest.raises(ValueError, match="too large"):
        web_ingest.read_html_response(FakeResponse(b"", "text/html", "9999999"))
    with pytest.raises(ValueError, match="too large"):
        web_ingest.read_html_response(FakeResponse(b"x" * 11, "text/html"), max_bytes=10)
