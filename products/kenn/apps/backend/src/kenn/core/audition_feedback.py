"""Bounded listener feedback for an exact, verified KENN audition.

Feedback is evidence for the next planning turn, not a Live mutation.  It is
accepted only against a verified applied audition receipt so the planner can
tell which exact clip was heard.
"""

from __future__ import annotations

import time
import uuid
from typing import Any


SCHEMA = "kenn.audition_feedback.v1"
AUDITION_RECEIPT_SCHEMA = "kenn.ableton_clip_audition_receipt.v1"
VERDICTS = frozenset({"keep", "revise", "reject"})
MAX_COMMENT = 1000
MAX_REQUESTED_CHANGES = 5
MAX_CHANGE_TEXT = 256


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _receipt_target(receipt: dict[str, Any]) -> dict[str, Any]:
    target = receipt.get("target")
    if not isinstance(target, dict):
        return {}
    return {
        "track_index": target.get("track_index"),
        "track_name": _text(target.get("track_name"), 256),
        "clip_slot_index": target.get("clip_slot_index"),
    }


def validate_audition_receipt(receipt: Any) -> tuple[dict[str, Any], list[str]]:
    """Return a safe receipt projection and validation errors."""
    if not isinstance(receipt, dict):
        return {}, ["receipt must be an object"]
    errors: list[str] = []
    if receipt.get("schema") != AUDITION_RECEIPT_SCHEMA:
        errors.append(f"receipt must use {AUDITION_RECEIPT_SCHEMA}")
    if receipt.get("status") != "applied":
        errors.append("receipt must describe an applied audition")
    if receipt.get("verified") is not True:
        errors.append("receipt must be verified by Live readback")
    receipt_id = _text(receipt.get("receipt_id"), 256)
    if not receipt_id:
        errors.append("receipt_id is required")
    target = _receipt_target(receipt)
    if not target.get("track_name"):
        errors.append("receipt target must contain track_name")
    for key in ("track_index", "clip_slot_index"):
        try:
            if int(target.get(key)) < 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"receipt target {key} must be a non-negative integer")
    projection = {
        "receipt_id": receipt_id,
        "action": _text(receipt.get("action"), 96),
        "target": target,
        "clip_fingerprint": _text(receipt.get("clip_fingerprint"), 128),
        "clip_length": receipt.get("clip_length"),
        "source_receipt_id": _text(receipt.get("source_receipt_id"), 256),
    }
    return projection, errors


def build_audition_feedback(
    *,
    session_id: str,
    receipt: dict[str, Any],
    verdict: str,
    rating: Any = None,
    comment: Any = "",
    requested_changes: Any = None,
) -> dict[str, Any]:
    """Validate and build a non-secret feedback record."""
    clean_session = _text(session_id, 128)
    if not clean_session:
        raise ValueError("session_id is required")
    receipt_projection, receipt_errors = validate_audition_receipt(receipt)
    if receipt_errors:
        raise ValueError("; ".join(receipt_errors))
    clean_verdict = _text(verdict, 32).lower()
    if clean_verdict not in VERDICTS:
        raise ValueError("verdict must be one of: keep, revise, reject")
    clean_comment = _text(comment, MAX_COMMENT)

    clean_rating: int | None = None
    if rating is not None and rating != "":
        try:
            clean_rating = int(rating)
        except (TypeError, ValueError):
            raise ValueError("rating must be an integer from 1 to 5") from None
        if not 1 <= clean_rating <= 5:
            raise ValueError("rating must be an integer from 1 to 5")

    if requested_changes is None:
        changes: list[str] = []
    elif isinstance(requested_changes, list):
        if len(requested_changes) > MAX_REQUESTED_CHANGES:
            raise ValueError(f"requested_changes may contain at most {MAX_REQUESTED_CHANGES} items")
        changes = [_text(item, MAX_CHANGE_TEXT) for item in requested_changes]
        if any(not item for item in changes):
            raise ValueError("requested_changes items must be non-empty strings")
    else:
        raise ValueError("requested_changes must be an array of strings")

    return {
        "schema": SCHEMA,
        "feedback_id": f"feedback-{uuid.uuid4().hex}",
        "session_id": clean_session,
        "source_receipt_id": receipt_projection["receipt_id"],
        "verdict": clean_verdict,
        "rating": clean_rating,
        "comment": clean_comment,
        "requested_changes": changes,
        "audition": receipt_projection,
        "created_at": time.time(),
        "advisory_only": True,
    }


__all__ = [
    "AUDITION_RECEIPT_SCHEMA",
    "SCHEMA",
    "VERDICTS",
    "build_audition_feedback",
    "validate_audition_receipt",
]
