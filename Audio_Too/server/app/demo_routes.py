"""Password-protected tester demo routes for Audio Tips LLM."""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

import ableton_bridge
import demo_auth
import demo_feedback
import enquiry_guard
import studio_tips

LogEvent = Callable[[str, str, str], None]


def safe_demo_analytics(payload: dict) -> dict:
    return {
        key: payload.get(key, 0)
        for key in (
            "total_recent_questions",
            "low_confidence",
            "weak_rate",
            "feedback_total",
            "useful",
            "needs_work",
            "feedback_rate",
        )
    }


def authorized(handler) -> bool:
    token = demo_auth.cookie_value(handler.headers.get("Cookie"))
    return demo_auth.verify_demo_token(token)


def session_id(handler) -> str:
    token = demo_auth.cookie_value(handler.headers.get("Cookie"))
    return demo_auth.demo_session_id(token)


def require_demo_auth(handler) -> bool:
    if authorized(handler):
        return True
    handler.send_json(401, {"error": "Demo password required."})
    return False


def handle_get(handler, path: str) -> bool:
    parsed = urlparse(path)
    route = parsed.path
    query = parse_qs(parsed.query)
    if route == "/api/demo/session":
        handler.send_json(
            200,
            {
                "configured": demo_auth.demo_configured(),
                "authenticated": authorized(handler),
                "session_id": session_id(handler) if authorized(handler) else "",
                "analytics": safe_demo_analytics(demo_feedback.analytics(limit=25)) if authorized(handler) else {},
            },
        )
        return True
    if route == "/api/demo/catalog":
        if not require_demo_auth(handler):
            return True
        handler.send_json(200, studio_tips.public_catalog())
        return True
    if route == "/api/demo/suggest":
        if not require_demo_auth(handler):
            return True
        text = (query.get("q") or [""])[0]
        handler.send_json(200, studio_tips.suggest_questions(text, limit=6))
        return True
    return False


def handle_post(handler, path: str, *, log_event: LogEvent) -> bool:
    if path == "/api/demo/login":
        if enquiry_guard.is_rate_limited(
            getattr(handler, "client_address", None), scope="demo_login"
        ):
            handler.send_json(429, {"error": "Too many demo login attempts. Try again later."})
            return True
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        if not demo_auth.demo_configured():
            handler.send_json(503, {"error": "Demo access is not configured on this server."})
            return True
        password = str(payload.get("password", ""))
        if not demo_auth.verify_password(password):
            handler.send_json(401, {"error": "Invalid demo password."})
            return True
        handler.send_json(
            200,
            {"ok": True, "authenticated": True},
            cookie=demo_auth.demo_cookie_header(),
        )
        log_event("demo_login", "tester signed in", "demo")
        return True

    if path == "/api/demo/logout":
        handler.send_json(
            200,
            {"ok": True, "authenticated": False},
            cookie=demo_auth.demo_cookie_header(clear=True),
        )
        return True

    if path == "/api/demo/ask":
        if not require_demo_auth(handler):
            return True
        try:
            payload = handler.read_json_body()
            question = studio_tips.validate_question(payload)
        except ValueError as exc:
            handler.send_json(400, {"error": str(exc)})
            return True
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        history = payload.get("history") if isinstance(payload.get("history"), list) else []
        client_session_id = str(payload.get("session_id", "")).strip()
        result = ableton_bridge.ask(
            question,
            limit=8,
            history=history,
            allow_llm=False,
            channel="demo",
            session_id=client_session_id,
            allow_generation=False,
        )
        demo_feedback.record_question(session_id(handler), question, result)
        result = studio_tips.safe_public_answer(result)
        result["disclaimer"] = studio_tips.DISCLAIMER
        result["demo"] = True
        handler.send_json(200, result)
        log_event("demo_question", question[:120], "demo")
        return True

    if path == "/api/demo/feedback":
        if not require_demo_auth(handler):
            return True
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        rating = str(payload.get("rating", "")).strip().lower()
        if rating not in {"useful", "not_useful"}:
            handler.send_json(400, {"error": "rating must be useful or not_useful."})
            return True
        payload["session_id"] = session_id(handler)
        payload["channel"] = "demo"
        row = demo_feedback.record_feedback(payload)
        log_event("demo_feedback", f"{rating}: {row.get('question', '')[:80]}", "demo")
        handler.send_json(
            201,
            {"ok": True, "feedback": {"id": row.get("id", ""), "rating": row.get("rating", "")}},
        )
        return True

    return False
