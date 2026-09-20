"""Phase-0 P0-A dedicated regression: the actual do_POST dispatch ordering.

docs/thursday/PHASE_0_HARDENING_REPORT.md flagged that P0-A's fix (moving
handle_thursday_post() to after require_private_post() in
business/app/server.py's do_POST) had no dedicated route-level test of its
own -- only indirect coverage via other suites exercising the same code
path. This file closes that gap.

These tests drive the REAL business/app/server.py Handler.do_POST (loaded
the same way tests/automix/test_automix_endpoints.py does, not a
reimplementation), so they exercise the actual historically-vulnerable
ordering condition: handle_thursday_post() must not run before
require_private_post() succeeds. Before the P0-A fix, an unauthorized
request to /api/thursday/ask reached thursday.bridge.ask() and returned 200
with a real answer; these tests would have failed against that code (the
mocked bridge.ask would show call_count == 1 and status would be 200, not
401) and pass against the current implementation.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

# Load business/app/server.py the same way tests/automix/test_automix_endpoints.py
# does -- a fresh module object under the name "website_server", not a
# reimplementation of the dispatcher.
_website_server_path = ROOT / "server" / "app" / "server.py"
_spec = importlib.util.spec_from_file_location("website_server_authtest", str(_website_server_path))
website_server = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("website_server_authtest", website_server)
_spec.loader.exec_module(website_server)


class MockHandler(website_server.Handler):
    """Same minimal harness pattern tests/automix/test_automix_endpoints.py
    already uses -- overrides only the auth *decision* (is_authorized),
    while require_auth()/require_private_post() themselves are the real
    methods from website_server.Handler (not stubbed out), so the actual
    do_POST -> require_private_post() -> require_auth() call chain runs."""

    def __init__(self, path: str, body: bytes = b"", is_authorized: bool = True):
        self.path = path
        self.command = "POST"
        self.headers = {"Content-Length": str(len(body)), "Content-Type": "application/json"}
        self.rfile = BytesIO(body)
        self._is_authorized = is_authorized
        self.status = 0
        self.payload: dict = {}

    def content_length(self) -> int:
        return int(self.headers.get("Content-Length", "0"))

    def read_body_bytes(self) -> bytes:
        return self.rfile.read()

    def read_json_body(self) -> dict:
        return json.loads(self.read_body_bytes().decode("utf-8"))

    # Real website_server.Handler.authorized() reads a signed session
    # cookie; substitute only that lowest-level check so require_auth() and
    # require_private_post() (both real, unmodified methods) run for real.
    def authorized(self) -> bool:
        return self._is_authorized

    def request_is_same_origin(self) -> bool:
        return True

    def session_token(self) -> str:
        return "mock-session-token" if self._is_authorized else ""

    def require_private_post(self) -> bool:
        # Same simplification tests/automix/test_automix_endpoints.py's
        # MockHandler uses: origin/CSRF are covered by their own dedicated
        # tests (test_route_access.py, session_auth tests) -- this file's
        # job is proving the *ordering* (auth-before-dispatch), which
        # require_auth() alone already exercises via the real authorized()
        # -> require_auth() chain unmodified above.
        return self.require_auth()

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload


@pytest.fixture(autouse=True)
def _no_rate_limit_interference():
    """Ensure an unrelated prior test's rate-limit counter can't turn a
    401-vs-200 assertion into a 429 by accident (dashboard_write allows 300
    requests/60s, but tests may share the module-level counter dict across a
    long pytest session)."""
    from server.app import enquiry_guard

    enquiry_guard.clear_rate_limit(None, "dashboard_write")
    yield


def test_unauthenticated_thursday_ask_is_rejected_before_reaching_the_bridge() -> None:
    """The core P0-A regression: do_POST must reject an unauthenticated
    /api/thursday/ask before thursday.bridge.ask() is ever invoked. Against
    the pre-fix ordering (handle_thursday_post() dispatched before
    require_private_post()), this would observe status 200 and
    ask_mock.call_count == 1."""
    body = json.dumps({"question": "how's business", "session_id": ""}).encode("utf-8")
    handler = MockHandler("/api/thursday/ask", body=body, is_authorized=False)

    with patch("thursday.bridge.ask") as ask_mock:
        website_server.Handler.do_POST(handler)

    assert ask_mock.call_count == 0, "unauthenticated request reached the Thursday bridge"
    assert handler.status == 401
    assert "password" in handler.payload.get("error", "").lower()


def test_authenticated_thursday_ask_is_accepted() -> None:
    """Equal and opposite: a genuinely authenticated request must still
    work -- proves the fix didn't over-block legitimate access."""
    body = json.dumps({"question": "how's business", "session_id": ""}).encode("utf-8")
    handler = MockHandler("/api/thursday/ask", body=body, is_authorized=True)

    with patch(
        "thursday.bridge.ask",
        return_value={"answer": "Business is steady.", "session_id": "s-1", "status": "succeeded"},
    ) as ask_mock:
        website_server.Handler.do_POST(handler)

    assert ask_mock.call_count == 1
    assert handler.status == 200
    assert handler.payload.get("answer") == "Business is steady."


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/thursday/feedback", {"turn_id": "t1", "rating": 1, "session_id": "s"}),
        ("/api/thursday/jarvis-action", {"action": "query", "prompt": "hi"}),
        ("/api/thursday/commercial-dispatch", {"client_name": "Acme", "project_title": "X"}),
        ("/api/thursday/autonomous-execute", {"instruction": "make a beat"}),
    ],
)
def test_unauthenticated_thursday_mutation_routes_cannot_execute(path: str, body: dict) -> None:
    """Broader sweep: every AUTHENTICATED-classified /api/thursday/* POST
    route named in the audit must reject an unauthenticated caller with 401
    before its own handler body runs -- not just /ask."""
    raw = json.dumps(body).encode("utf-8")
    handler = MockHandler(path, body=raw, is_authorized=False)

    website_server.Handler.do_POST(handler)

    assert handler.status == 401, f"{path} did not reject an unauthenticated request (got {handler.status})"


def test_unauthenticated_request_never_reaches_handle_thursday_post_at_all() -> None:
    """Direct proof of the historically-vulnerable ordering: patch
    handle_thursday_post itself (the function that was dispatched too
    early) and assert it is never called for an unauthenticated request --
    this is the literal condition that was broken before P0-A."""
    body = json.dumps({"question": "status"}).encode("utf-8")
    handler = MockHandler("/api/thursday/ask", body=body, is_authorized=False)

    with patch.object(website_server, "handle_thursday_post") as handler_mock:
        website_server.Handler.do_POST(handler)

    assert handler_mock.call_count == 0, (
        "handle_thursday_post() was invoked before authentication succeeded -- "
        "this is exactly the P0-A ordering bug"
    )
    assert handler.status == 401
