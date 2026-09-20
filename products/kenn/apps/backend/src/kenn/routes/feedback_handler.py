"""HTTP route handlers for user feedback, session feedback, and audition feedback."""

from __future__ import annotations

import logging
from typing import Any

from kenn.core.audition_feedback import build_audition_feedback
from kenn.core.feedback_input import (
    FeedbackInputError,
    optional_bool,
    optional_nonnegative_float,
    optional_rating,
)
from kenn.core.session_memory import save_audition_feedback, save_session_feedback

logger = logging.getLogger("kenn.feedback")

try:
    import demo_feedback
except ImportError:
    demo_feedback = None


def handle_feedback(handler: Any, payload: dict) -> None:
    if not demo_feedback:
        handler.send_json(503, {"error": "Feedback storage is unavailable."})
        return
    rating = str(payload.get("rating", "")).strip().lower()
    if rating not in {"useful", "not_useful"}:
        handler.send_json(400, {"error": "rating must be useful or not_useful."})
        return
    feedback_kind = str(payload.get("kind", "")).strip().lower()
    payload["channel"] = "mix_review" if feedback_kind == "mix_review" else "main_chat"
    row = demo_feedback.record_feedback(payload)
    handler.send_json(201, {"ok": True, "feedback": row})


def handle_session_feedback(handler: Any, payload: dict) -> None:
    turn_id = str(payload.get("turn_id", "")).strip()
    if not turn_id:
        handler.send_json(400, {"error": "turn_id is required."})
        return

    try:
        explicit_rating = optional_rating(payload.get("explicit_rating"))
        dwell_seconds = optional_nonnegative_float(payload.get("dwell_seconds"), field="dwell_seconds")
        has_followup = optional_bool(payload.get("has_followup"), field="has_followup")
        followup_interval_seconds = optional_nonnegative_float(
            payload.get("followup_interval_seconds"), field="followup_interval_seconds"
        )
    except FeedbackInputError as exc:
        handler.send_json(400, {"error": str(exc)})
        return

    route = payload.get("route")
    if route is not None:
        route = str(route).strip()
    topics = payload.get("topics")

    save_session_feedback(
        turn_id=turn_id,
        explicit_rating=explicit_rating,
        dwell_seconds=dwell_seconds,
        has_followup=has_followup,
        followup_interval_seconds=followup_interval_seconds,
        route=route,
        topics=topics,
    )

    correction = payload.get("correction") or payload.get("correction_text")
    if correction:
        try:
            from kenn.knowledge import ingest_correction

            ingest_correction(turn_id, str(correction).strip())
        except Exception as e:
            logger.warning(f"Failed to ingest feedback correction: {e}")

    handler.send_json(200, {"ok": True})


def handle_audition_feedback(handler: Any, payload: dict) -> None:
    """Record listener evidence without opening a Live mutation path."""
    try:
        feedback = build_audition_feedback(
            session_id=str(payload.get("session_id", "")),
            receipt=payload.get("receipt"),
            verdict=str(payload.get("verdict", "")),
            rating=payload.get("rating"),
            comment=payload.get("comment", ""),
            requested_changes=payload.get("requested_changes"),
        )
    except (TypeError, ValueError) as exc:
        handler.send_json(400, {"ok": False, "error": str(exc), "advisory_only": True})
        return
    if not save_audition_feedback(feedback):
        handler.send_json(503, {"ok": False, "error": "Audition feedback could not be persisted.", "advisory_only": True})
        return
    next_actions = []
    if feedback["verdict"] == "revise":
        next_actions.append({
            "action": "create_revision_proposal",
            "description": "Use the requested changes as advisory input; inspect Live and create a new confirmation-only proposal.",
            "source_feedback_id": feedback["feedback_id"],
        })
    handler.send_json(201, {
        "ok": True,
        "feedback": feedback,
        "next_actions": next_actions,
        "advisory_only": True,
    })

