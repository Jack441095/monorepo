"""Tests for the /kenn proxy rework (Phase 1 follow-up,
docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md): app.js now calls
/kenn/api/... uniformly, so the standalone server must serve identical
results under both the bare /api/... path and the /kenn/api/... path."""

from __future__ import annotations

import io
from urllib.parse import urlparse

from kenn import server


def test_strip_kenn_prefix_bare_root():
    parsed = server._strip_kenn_prefix(urlparse("/kenn"))
    assert parsed.path == "/"


def test_strip_kenn_prefix_root_with_trailing_slash():
    parsed = server._strip_kenn_prefix(urlparse("/kenn/"))
    assert parsed.path == "/"


def test_strip_kenn_prefix_api_path():
    parsed = server._strip_kenn_prefix(urlparse("/kenn/api/health"))
    assert parsed.path == "/api/health"


def test_strip_kenn_prefix_static_asset():
    parsed = server._strip_kenn_prefix(urlparse("/kenn/app.js"))
    assert parsed.path == "/app.js"


def test_strip_kenn_prefix_preserves_query_string():
    parsed = server._strip_kenn_prefix(urlparse("/kenn/api/session?id=abc123"))
    assert parsed.path == "/api/session"
    assert parsed.query == "id=abc123"


def test_strip_kenn_prefix_leaves_unrelated_paths_unchanged():
    parsed = server._strip_kenn_prefix(urlparse("/api/health"))
    assert parsed.path == "/api/health"
    parsed2 = server._strip_kenn_prefix(urlparse("/kennel"))  # must not partial-match
    assert parsed2.path == "/kennel"


class FakeHandler:
    def __init__(self, path: str) -> None:
        self.path = path
        self.headers = {}
        self.status = 0
        self.payload = None
        self.rfile = io.BytesIO()

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload

    def send_cors_headers(self) -> None:
        pass

    def allowed_cors_origin(self) -> str:
        return ""

    def enforce_rate_limit(self, _scope: str) -> bool:
        return True


def test_health_endpoint_identical_under_bare_and_kenn_prefixed_path():
    bare = FakeHandler("/api/health")
    server.Handler.do_GET(bare)
    prefixed = FakeHandler("/kenn/api/health")
    server.Handler.do_GET(prefixed)

    assert bare.status == 200 == prefixed.status
    assert bare.payload == prefixed.payload
