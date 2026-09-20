"""Trust-boundary matrix tests for Website routes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBSITE = ROOT / "server" / "app"
if str(WEBSITE) not in sys.path:
    sys.path.insert(0, str(WEBSITE))
spec = importlib.util.spec_from_file_location("route_access_website_server", WEBSITE / "server.py")
assert spec and spec.loader
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

def test_public_and_token_get_routes_are_explicit() -> None:
    for path in server.PUBLIC_GET_ROUTES:
        assert server.route_access("GET", path) == "public"
    assert server.route_access("GET", "/invoice/inv-1") == "signed-token"
    assert server.route_access("GET", "/dashboard") == "public-static"


def test_canonical_static_routes_are_explicit() -> None:
    assert server.STATIC_ROUTE_MAP["/"] == "/index.html"
    assert server.STATIC_ROUTE_MAP["/hub"] == "/hub.html"
    assert server.STATIC_ROUTE_MAP["/dashboard"] == "/dashboard.html"
    assert server.STATIC_ROUTE_MAP["/thursday"] == "/thursday.html"
    assert server.STATIC_ROUTE_MAP["/creative-lab"] == "/creative-lab.html"
    assert server.STATIC_ROUTE_MAP["/audio-analysis"] == "/audio-analysis.html"
    assert server.STATIC_ROUTE_MAP["/automix"] == "/automix.html"
    assert server.STATIC_ROUTE_MAP["/portfolio"] == "/portfolio.html"
    assert server.STATIC_ROUTE_MAP["/demo"] == "/demo.html"


def test_private_get_families_fail_closed() -> None:
    paths = [
        "/api/admin/dashboard",
        "/api/admin/new-future-route",
        "/api/ableton/gaps",
        "/api/ableton/query-audio",
        "/api/ableton/new-future-route",
        "/api/automix/status",
        "/api/automix/download/project-1",
        "/api/v1/openapi.json",
        "/api/v1/automix/jobs",
        "/api/activity",
        "/api/summary",
        "/api/records",
        "/api/invoices",
        "/kenn/api/session",
        "/kenn/api/sessions",
    ]
    assert all(server.route_access("GET", path) == "authenticated-read" for path in paths)


def test_kenn_proxy_static_shell_stays_public_but_api_requires_auth() -> None:
    """Regression test: /kenn/api/* proxies private KENN session/chat data to
    the KENN engine on 8090 (which has no auth of its own) and must require a
    dashboard session, unlike the static shell files it sits next to."""
    for path in ("/kenn", "/kenn/", "/kenn/index.html", "/kenn/app.js", "/kenn/styles.css"):
        assert server.route_access("GET", path) != "authenticated-read"
    assert server.route_access("GET", "/kenn/api/session") == "authenticated-read"
    assert server.route_access("GET", "/kenn/api/sessions") == "authenticated-read"
    assert server.route_access("GET", "/kenn/api/anything-future") == "authenticated-read"


def test_post_matrix_defaults_api_writes_to_authenticated() -> None:
    for path in server.PUBLIC_POST_ROUTES:
        assert server.route_access("POST", path) == "public"
    assert server.route_access("POST", "/api/auth/logout") == "authenticated-write"
    assert server.route_access("POST", "/api/admin/new-future-route") == "authenticated-write"
    assert server.route_access("POST", "/api/ableton/new-future-route") == "authenticated-write"
    assert server.route_access("POST", "/api/automix/new-future-route") == "authenticated-write"


def test_demo_routes_remain_in_their_separate_auth_boundary() -> None:
    assert server.route_access("GET", "/api/demo/session") == "demo"
    assert server.route_access("POST", "/api/demo/ask") == "demo"


def test_server_errors_hide_internal_details() -> None:
    payload = server.safe_error_payload(
        500,
        {"ok": False, "error": "database failed at /private/client/alex.db"},
        "error123",
    )
    assert payload == {
        "ok": False,
        "error": "The request could not be completed.",
        "code": "internal_error",
        "message": "The request could not be completed.",
        "details": {},
        "request_id": "error123",
    }
    assert server.safe_error_payload(400, {"error": "Invalid field."}, "request123") == {
        "error": "Invalid field.",
        "code": "invalid_request",
        "message": "Invalid field.",
        "details": {},
        "request_id": "request123",
    }


def test_structured_error_preserves_validation_details_and_legacy_message() -> None:
    payload = server.safe_error_payload(
        400,
        {
            "error": "project_id is invalid.",
            "code": "validation_error",
            "details": {"field": "project_id"},
        },
        "request456",
    )
    assert payload == {
        "error": "project_id is invalid.",
        "code": "validation_error",
        "message": "project_id is invalid.",
        "details": {"field": "project_id"},
        "request_id": "request456",
    }
