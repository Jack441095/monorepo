"""Authentication and session management GET/POST routes."""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import urlparse

import enquiry_guard
import session_auth


def _is_localhost(handler) -> bool:
    addr = getattr(handler, "client_address", ("",))[0]
    return addr in {"127.0.0.1", "::1", "localhost"}


def handle_auth_get(handler, parsed_path: str) -> bool:
    """Handle /api/auth/* GET routes. Returns True if handled."""
    parsed = urlparse("https://host" + parsed_path)
    if parsed.path == "/api/auth/session":
        token = handler.session_token()
        authenticated = session_auth.verify_session_token(token)

        # In dev mode, auto-issue a session for localhost so Thursday/KENN
        # endpoints work without a manual browser login.
        cookie = None
        if not authenticated and session_auth.development_mode() and _is_localhost(handler):
            token = session_auth.make_session_token()
            authenticated = True
            cookie = session_auth.session_cookie_header(token=token)

        handler.send_json(
            200,
            {
                "authenticated": authenticated,
                "csrf_token": session_auth.make_csrf_token(token) if authenticated else "",
            },
            cookie=cookie,
        )
        return True
    return False


def handle_auth_post(handler, parsed_path: str, *, log_event: Callable[[str, str, str], None]) -> bool:
    """Handle /api/auth/* POST routes. Returns True if handled."""
    parsed = urlparse("https://host" + parsed_path)
    path = parsed.path

    if path == "/api/auth/login":
        if not handler.request_is_same_origin():
            handler.send_json(403, {"error": "Cross-origin request rejected."})
            return True
        if enquiry_guard.is_rate_limited(handler.client_address, scope="dashboard_login"):
            log_event("dashboard_login_blocked", "too many failed attempts", "security")
            handler.send_json(429, {"error": "Too many login attempts. Try again later."})
            return True
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        password = str(payload.get("password", ""))
        if not session_auth.verify_password(password):
            log_event("dashboard_login_failed", "invalid password", "security")
            handler.send_json(401, {"error": "Invalid password."})
            return True
        enquiry_guard.clear_rate_limit(handler.client_address, scope="dashboard_login")
        log_event("dashboard_login_succeeded", "dashboard session issued", "security")
        token = session_auth.make_session_token()
        handler.send_json(
            200,
            {
                "ok": True,
                "authenticated": True,
                "csrf_token": session_auth.make_csrf_token(token),
            },
            cookie=session_auth.session_cookie_header(token=token),
        )
        return True

    if path == "/api/auth/logout":
        if not handler.require_private_post():
            return True
        session_auth.revoke_session_token(handler.session_token())
        handler.send_json(
            200,
            {"ok": True, "authenticated": False},
            cookie=session_auth.session_cookie_header(clear=True),
        )
        return True

    return False
