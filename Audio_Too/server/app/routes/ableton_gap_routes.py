"""Knowledge-gap mutation routes for the Ableton/KENN dashboard."""

from __future__ import annotations

import json
from collections.abc import Callable

import ableton_bridge
import lm_gaps


def handle_ableton_gap_post(
    handler,
    path: str,
    *,
    log_event: Callable[[str, str, str], None],
) -> bool:
    if path == "/api/ableton/gaps/create-note":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        gap_id = str(payload.get("id", "")).strip()
        if not gap_id:
            handler.send_json(400, {"error": "id is required."})
            return True
        result = ableton_bridge.create_note_from_gap(gap_id)
        if result.get("ok"):
            log_event("tips_gap_note_created", result.get("note", gap_id), "dashboard")
            handler.send_json(200, result)
        else:
            status = 404 if "not found" in str(result.get("error", "")).lower() else 400
            handler.send_json(status, result)
        return True

    if path == "/api/ableton/gaps/dismiss":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        gap_id = str(payload.get("id", "")).strip()
        if not gap_id:
            handler.send_json(400, {"error": "id is required."})
            return True
        if lm_gaps.dismiss_gap(gap_id):
            log_event("tips_gap_dismissed", gap_id, "dashboard")
            handler.send_json(200, {"ok": True, "id": gap_id})
        else:
            handler.send_json(404, {"error": "Gap not found or already dismissed."})
        return True

    if path == "/api/ableton/gaps/retest":
        length = int(handler.headers.get("Content-Length", "0"))
        try:
            payload = handler.read_json_body() if length > 0 else {}
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        gap_id = str(payload.get("id", "")).strip()
        result = lm_gaps.retest_gap(gap_id) if gap_id else lm_gaps.retest_all_open()
        if result.get("ok"):
            log_event("tips_gap_retested", gap_id or "all", "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/ableton/gaps/create-note-from-question":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        question = str(payload.get("question", "")).strip()
        if not question:
            handler.send_json(400, {"error": "question is required."})
            return True
        topics = payload.get("topics") if isinstance(payload.get("topics"), list) else []
        result = ableton_bridge.create_note_from_question_api(question, topics)
        if result.get("ok"):
            log_event("tips_gap_note_created", result.get("note", ""), "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    return False
