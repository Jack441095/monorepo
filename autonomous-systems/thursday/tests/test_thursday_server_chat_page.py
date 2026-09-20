"""Tests for thursday/server.py's /chat route -- a static, same-origin
mobile chat page (added 2026-09-02 so Thursday can be reached over
Tailscale without a hosted page hitting CORS/mixed-content blocking
against a plain-HTTP, Tailscale-only server).
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thursday import server as ts  # noqa: E402


class _FakeHandler:
    def __init__(self, path: str):
        self.path = path
        self.sent: dict = {}

    def _send_html(self, status, body):
        self.sent = {"kind": "html", "status": status, "body": body}

    def _send_error(self, status, message, code=""):
        self.sent = {"kind": "error", "status": status, "message": message, "code": code}

    def _send_json(self, status, payload, **kw):
        self.sent = {"kind": "json", "status": status, "payload": payload}

    def _handle_health(self):
        self.sent = {"kind": "health"}


def test_root_path_serves_the_chat_page():
    handler = _FakeHandler("/")
    ts.Handler.do_GET(handler)
    assert handler.sent["kind"] == "html"
    assert handler.sent["status"] == 200
    assert b"Thursday" in handler.sent["body"]


def test_chat_path_serves_the_same_page():
    handler = _FakeHandler("/chat")
    ts.Handler.do_GET(handler)
    assert handler.sent["kind"] == "html"
    assert handler.sent["status"] == 200


def test_page_has_a_100vh_fallback_before_100dvh():
    # Regression guard for a real bug found live 2026-09-02: a browser
    # that doesn't understand 100dvh must not be left with zero height on
    # html/body -- that produced a genuinely blank page (every element
    # present in the DOM, nothing visible, because the flex column had no
    # height to lay out into). The 100vh declaration must appear BEFORE
    # 100dvh so an unsupporting browser keeps it (CSS takes the last
    # understood declaration) while a supporting one still ends up on
    # 100dvh.
    html = (Path(ts.__file__).resolve().parent / "static" / "chat.html").read_text()
    vh_index = html.index("height: 100vh")
    dvh_index = html.index("height: 100dvh")
    assert vh_index < dvh_index
    assert "html, body { height: 100%; }" in html


def test_page_supports_a_url_token_for_home_screen_bookmarks():
    # Founder-requested fix: iOS "Add to Home Screen" web apps can lose
    # localStorage more aggressively than a normal tab, forcing the token
    # prompt every reopen. A ?token=... URL param must be read on load,
    # saved, and used to skip the gate immediately -- checked at the JS
    # source level (no browser in this test suite) rather than only
    # asserting the function exists, so a future edit that keeps the
    # function but forgets to call it on load still fails this test.
    html = (Path(ts.__file__).resolve().parent / "static" / "chat.html").read_text()
    assert "function tokenFromUrl()" in html
    assert "var urlToken = tokenFromUrl();" in html
    assert "if (urlToken) {" in html
    # The URL-token branch must save it (setToken) before starting chat,
    # so the bookmark keeps working even if the URL itself isn't reopened
    # next time (e.g. localStorage happens to survive that once).
    url_branch = html[html.index("if (urlToken) {"):html.index("} else if (getToken())")]
    assert "setToken(urlToken)" in url_branch
    assert "startChat()" in url_branch


def test_chat_page_is_not_gated_behind_auth():
    # No _is_authorised check before serving -- the page itself carries no
    # secrets (the token is entered client-side into localStorage); only
    # the actual /ask calls it makes are auth-checked.
    handler = _FakeHandler("/chat")
    ts.Handler.do_GET(handler)
    assert handler.sent["kind"] == "html"


def test_chat_page_never_embeds_the_real_server_token(monkeypatch):
    monkeypatch.setenv("THURSDAY_SERVER_TOKEN", "super-secret-token-value")
    handler = _FakeHandler("/chat")
    ts.Handler.do_GET(handler)
    assert b"super-secret-token-value" not in handler.sent["body"]


def test_static_chat_html_file_exists_on_disk():
    static_path = Path(ts.__file__).resolve().parent / "static" / "chat.html"
    assert static_path.exists()


def test_health_endpoint_still_dispatches_correctly():
    # Regression guard: adding the "" / "/chat" branch must not have
    # displaced the existing /health route.
    handler = _FakeHandler("/health")
    ts.Handler.do_GET(handler)
    assert handler.sent == {"kind": "health"}


def test_unknown_path_still_404s():
    handler = _FakeHandler("/totally-unknown-path")
    ts.Handler.do_GET(handler)
    assert handler.sent["kind"] == "error"
    assert handler.sent["status"] == 404
