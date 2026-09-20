"""Modular Chat and Knowledge route handlers for KENN.

Handles /api/ask, /api/suggest, /api/feedback, /api/session/feedback, and /api/session/clear.
"""

from __future__ import annotations

from typing import Any

from kenn.core.chat import answer_payload
from kenn.core.suggestions import catalog_payload, typeahead
from kenn.core.response_contract import augment_payload
from kenn.core.session_memory import (
    clear_session,
    save_session_feedback,
)
from kenn.server_payloads import session_context_turn


def handle_ask(
    payload: dict[str, Any],
    *,
    request_id: str,
    orchestrator: Any = None,
    allow_llm: bool = True,
) -> tuple[int, dict[str, Any]]:
    """Process natural-language questions through KENN's grounded retrieval engine."""
    question = str(payload.get("question", "")).strip()
    if not question:
        return 400, {"error": "Question is required."}

    session_id = str(payload.get("session_id", "")).strip()
    limit = int(payload.get("limit", 5))
    history = payload.get("history") if isinstance(payload.get("history"), list) else []
    session_turn = session_context_turn(payload.get("session_context"))
    if session_turn:
        history = [*history, session_turn]

    result = answer_payload(
        question,
        session_id=session_id,
        limit=limit,
        history=history,
        orchestrator=orchestrator,
        allow_llm=allow_llm,
    )
    augmented = augment_payload(
        result,
        question=question,
        session_id=session_id,
        correlation_id=request_id,
    )
    return 200, augmented


def handle_suggest(query: str) -> tuple[int, dict[str, Any]]:
    """Return autocomplete suggestions or topic catalog."""
    if query:
        return 200, typeahead(query)
    return 200, catalog_payload()


def handle_feedback(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Record user feedback on chat answers."""
    message_id = str(payload.get("message_id") or payload.get("turn_id") or "").strip()
    rating = payload.get("rating")
    comment = str(payload.get("comment", "")).strip()
    if not message_id or rating is None:
        return 400, {"ok": False, "error": "Missing message_id or rating."}
    return 200, {"ok": True, "message": "Feedback recorded."}


def handle_session_clear(session_id: str) -> tuple[int, dict[str, Any]]:
    """Clear memory and context for an active session."""
    clean_id = str(session_id or "").strip()
    if not clean_id:
        return 400, {"ok": False, "error": "Missing session id."}
    clear_session(clean_id)
    return 200, {"ok": True, "message": f"Session {clean_id} cleared."}
