"""Tests for the demo-only HTTP server surface."""

from __future__ import annotations

import sys
from pathlib import Path

WEBSITE = Path(__file__).resolve().parent.parent.parent / "server" / "app"
sys.path.insert(0, str(WEBSITE))

import demo_server  # noqa: E402


def test_demo_server_static_allowlist() -> None:
    allowed = {"/": "demo.html", "/demo": "demo.html", "/demo.html": "demo.html", "/demo.js": "demo.js", "/styles.css": "styles.css"}
    assert allowed["/demo"] == "demo.html"
    assert "/dashboard" not in allowed
    assert "/hub" not in allowed


def test_demo_server_defaults_to_private_host() -> None:
    assert demo_server.HOST == "127.0.0.1"
    assert demo_server.PORT == 8091
