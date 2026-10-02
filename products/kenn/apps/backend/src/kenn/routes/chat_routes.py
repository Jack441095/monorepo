"""Modular Chat and Knowledge route handlers for KENN.

Handles /api/ask, /api/suggest, /api/feedback, /api/session/feedback, and /api/session/clear.
"""

from __future__ import annotations

from typing import Any

from kenn.core import answer_upgrades
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
    allow_llm: bool = True,
) -> tuple[int, dict[str, Any]]:
    """Process natural-language questions through KENN's grounded retrieval engine."""
    question = str(payload.get("question") or "").strip()
    if not question:
        return 400, {"error": "Question is required."}

    session_id = str(payload.get("session_id") or "").strip()
    plugin_session_id = str(payload.get("plugin_session_id") or "").strip()
    limit = int(payload["limit"]) if payload.get("limit") is not None else 5
    history = payload.get("history") if isinstance(payload.get("history"), list) else []
    session_turn = session_context_turn(payload.get("session_context"))
    if session_turn:
        history = [*history, session_turn]

    # A chat turn from this route also supersedes its earlier background answer.
    answer_upgrades.begin_turn(session_id)
    result = answer_payload(
        question,
        session_id=session_id,
        plugin_session_id=plugin_session_id,
        limit=limit,
        history=history,
        correlation_id=request_id,
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
    answer_upgrades.invalidate(clean_id)
    clear_session(clean_id)
    return 200, {"ok": True, "message": f"Session {clean_id} cleared."}


def handle_get_memory(session_id: str) -> tuple[int, dict[str, Any]]:
    """Retrieve active producer preferences and episodic memories for a session."""
    clean_id = str(session_id or "").strip()
    if not clean_id:
        return 400, {"ok": False, "error": "session_id is required."}
    from kenn.core.assistant_profile_memory import AssistantProfileStore
    store = AssistantProfileStore()
    return 200, {
        "ok": True,
        "session_id": clean_id,
        "producer_preferences": store.current_preferences(clean_id),
        "episodic_outcomes": store.recent_episodes(clean_id),
    }


def handle_record_preference(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Record an explicit, opt-in producer preference."""
    session_id = str(payload.get("session_id", "")).strip()
    key = str(payload.get("key", "")).strip()
    value = str(payload.get("value", "")).strip()
    source_turn_id = str(payload.get("source_turn_id", "")).strip() or "turn-ui"
    user_statement = str(payload.get("user_statement", "")).strip()
    if not user_statement:
        user_statement = f"I prefer {value}" if value else ""

    from kenn.core.assistant_profile_memory import AssistantProfileStore
    store = AssistantProfileStore()
    result = store.record_preference(
        session_id=session_id,
        key=key,
        value=value,
        source_turn_id=source_turn_id,
        user_statement=user_statement,
    )
    status = 200 if result.get("ok") else 400
    return status, result


def handle_preference_history(session_id: str, key: str | None = None) -> tuple[int, dict[str, Any]]:
    """List superseded preferences so a producer can compare and go back."""
    clean_id = str(session_id or "").strip()
    if not clean_id:
        return 400, {"ok": False, "error": "session_id is required."}
    from kenn.core.assistant_profile_memory import AssistantProfileStore
    store = AssistantProfileStore()
    return 200, {"ok": True, "session_id": clean_id,
                 "superseded_preferences": store.preference_history(clean_id, key=key or None)}


def handle_restore_preference(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Reactivate a superseded preference by id, moving the current one back into history."""
    session_id = str(payload.get("session_id", "")).strip()
    preference_id = str(payload.get("preference_id", "")).strip()
    if not session_id or not preference_id:
        return 400, {"ok": False, "error": "session_id and preference_id are required."}
    from kenn.core.assistant_profile_memory import AssistantProfileStore
    store = AssistantProfileStore()
    result = store.restore_preference(session_id=session_id, preference_id=preference_id)
    return (200 if result.get("ok") else 404), result


def handle_delete_preference(session_id: str, key: str) -> tuple[int, dict[str, Any]]:
    """Forget an explicit producer preference."""
    clean_id = str(session_id or "").strip()
    clean_key = str(key or "").strip()
    if not clean_id or not clean_key:
        return 400, {"ok": False, "error": "session_id and key are required."}
    from kenn.core.assistant_profile_memory import AssistantProfileStore
    store = AssistantProfileStore()
    forgotten = store.forget_preference(session_id=clean_id, key=clean_key)
    return 200, {"ok": True, "session_id": clean_id, "key": clean_key, "forgotten": forgotten}


def handle_delete_episode(session_id: str, episode_id: str) -> tuple[int, dict[str, Any]]:
    """Forget an episodic outcome."""
    clean_id = str(session_id or "").strip()
    clean_ep = str(episode_id or "").strip()
    if not clean_id or not clean_ep:
        return 400, {"ok": False, "error": "session_id and episode_id are required."}
    from kenn.core.assistant_profile_memory import AssistantProfileStore
    store = AssistantProfileStore()
    forgotten = store.forget_episode(session_id=clean_id, episode_id=clean_ep)
    return 200, {"ok": True, "session_id": clean_id, "episode_id": clean_ep, "forgotten": forgotten}


def handle_clear_memory(session_id: str) -> tuple[int, dict[str, Any]]:
    """Clear all profile preferences and episodic memory for a session."""
    clean_id = str(session_id or "").strip()
    if not clean_id:
        return 400, {"ok": False, "error": "session_id is required."}
    from kenn.core.assistant_profile_memory import AssistantProfileStore
    store = AssistantProfileStore()
    cleared = store.clear_profile(clean_id)
    return 200, {"ok": True, "session_id": clean_id, "cleared": cleared}

