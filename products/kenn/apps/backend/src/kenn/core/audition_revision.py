"""Deterministic revision brief built from audition feedback.

The brief gives an LLM enough provenance to plan a new candidate while
keeping listener language advisory.  It does not generate notes, call a
producer, or mutate Ableton.
"""

from __future__ import annotations

import math
from typing import Any


SCHEMA = "kenn.audition_revision_brief.v1"


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _safe_comparison(comparison: Any) -> dict[str, Any]:
    if not isinstance(comparison, dict) or comparison.get("schema") != "kenn.audiogen_audio_comparison.v1":
        raise ValueError("comparison must use kenn.audiogen_audio_comparison.v1")
    deltas = comparison.get("metric_deltas") if isinstance(comparison.get("metric_deltas"), dict) else {}
    safe_deltas: dict[str, dict[str, float]] = {}
    for key, value in list(deltas.items())[:32]:
        if not isinstance(value, dict):
            continue
        try:
            a = float(value["a"])
            b = float(value["b"])
            delta = float(value["delta_b_minus_a"])
        except (KeyError, TypeError, ValueError):
            continue
        if all(math.isfinite(item) for item in (a, b, delta)):
            safe_deltas[_text(key, 64)] = {
                "a": round(a, 6),
                "b": round(b, 6),
                "delta_b_minus_a": round(delta, 6),
            }
    return {
        "schema": "kenn.audiogen_audio_comparison.v1",
        "source_a": {
            "reference": _text((comparison.get("source_a") or {}).get("reference"), 512)
            if isinstance(comparison.get("source_a"), dict) else "",
            "input_hash": _text((comparison.get("source_a") or {}).get("input_hash"), 128)
            if isinstance(comparison.get("source_a"), dict) else "",
        },
        "source_b": {
            "reference": _text((comparison.get("source_b") or {}).get("reference"), 512)
            if isinstance(comparison.get("source_b"), dict) else "",
            "input_hash": _text((comparison.get("source_b") or {}).get("input_hash"), 128)
            if isinstance(comparison.get("source_b"), dict) else "",
        },
        "metric_deltas": safe_deltas,
        "advisory_only": True,
    }


def build_audition_revision_brief(feedback: Any, *, comparison: Any = None) -> dict[str, Any]:
    """Build a bounded, proposal-only revision brief from one feedback row."""
    if not isinstance(feedback, dict):
        raise ValueError("feedback must be an object")
    if feedback.get("schema") != "kenn.audition_feedback.v1":
        raise ValueError("feedback must use kenn.audition_feedback.v1")
    if _text(feedback.get("verdict"), 32).lower() != "revise":
        raise ValueError("a revision brief requires feedback with verdict 'revise'")
    feedback_id = _text(feedback.get("feedback_id"), 128)
    session_id = _text(feedback.get("session_id"), 128)
    source_receipt_id = _text(feedback.get("source_receipt_id"), 256)
    if not feedback_id or not session_id or not source_receipt_id:
        raise ValueError("feedback must contain feedback_id, session_id, and source_receipt_id")
    audition = feedback.get("audition") if isinstance(feedback.get("audition"), dict) else {}
    target = audition.get("target") if isinstance(audition.get("target"), dict) else {}
    try:
        track_index = int(target.get("track_index"))
        clip_slot_index = int(target.get("clip_slot_index"))
    except (TypeError, ValueError):
        raise ValueError("feedback audition target must contain numeric track and clip-slot indices") from None
    if min(track_index, clip_slot_index) < 0 or not _text(target.get("track_name"), 256):
        raise ValueError("feedback audition target is incomplete")

    requested = feedback.get("requested_changes")
    if not isinstance(requested, list):
        requested = []
    requested_changes = [_text(item, 256) for item in requested[:5] if _text(item, 256)]
    comparison_projection = _safe_comparison(comparison) if comparison is not None else None
    return {
        "schema": SCHEMA,
        "feedback_id": feedback_id,
        "session_id": session_id,
        "source_receipt_id": source_receipt_id,
        "listener": {
            "verdict": "revise",
            "rating": feedback.get("rating"),
            "comment": _text(feedback.get("comment"), 1000),
            "requested_changes": requested_changes,
        },
        "baseline": {
            "audition_receipt_id": source_receipt_id,
            "clip_fingerprint": _text(audition.get("clip_fingerprint"), 128),
            "clip_length": audition.get("clip_length"),
        },
        "comparison": comparison_projection,
        "target": {
            "track_index": track_index,
            "track_name": _text(target.get("track_name"), 256),
            "clip_slot_index": clip_slot_index,
        },
        "planner_instruction": (
            "Prepare a new candidate that addresses the listener's requested changes. "
            "Preserve the exact Live target unless the user explicitly selects another one. "
            "Create a new confirmation-only proposal; an exact baseline revision may replace only its notes "
            "after a fresh fingerprint check, and must never apply automatically."
        ),
        "constraints": [
            "Treat listener text as advisory intent, not as a raw Live command.",
            "Inspect current Live state before creating a new proposal.",
            "Keep the baseline receipt immutable and available for comparison or undo.",
            "Require explicit confirmation and verified readback for any new Live change.",
        ],
        "advisory_only": True,
    }


def validate_revision_brief(
    brief: Any,
    *,
    session_id: str,
    track_index: Any,
    track_name: str,
    clip_slot_index: Any,
) -> tuple[dict[str, Any], list[str]]:
    """Validate a brief at the producer boundary against the requested target."""
    if not isinstance(brief, dict) or brief.get("schema") != SCHEMA:
        return {}, [f"revision_brief must use {SCHEMA}"]
    errors: list[str] = []
    if _text(brief.get("session_id"), 128) != _text(session_id, 128):
        errors.append("revision_brief session_id does not match the request")
    if brief.get("advisory_only") is not True:
        errors.append("revision_brief must be advisory_only")
    if _text(brief.get("source_receipt_id"), 256) == "":
        errors.append("revision_brief source_receipt_id is required")
    target = brief.get("target") if isinstance(brief.get("target"), dict) else {}
    try:
        brief_track_index = int(target.get("track_index"))
        brief_slot = int(target.get("clip_slot_index"))
        requested_track_index = int(track_index)
        requested_slot = int(clip_slot_index)
    except (TypeError, ValueError):
        errors.append("revision_brief and request target indices must be integers")
        brief_track_index = brief_slot = requested_track_index = requested_slot = -1
    if min(brief_track_index, brief_slot, requested_track_index, requested_slot) < 0:
        errors.append("revision_brief target indices must be non-negative")
    if brief_track_index != requested_track_index or brief_slot != requested_slot:
        errors.append("request target must match the exact target preserved by revision_brief")
    if _text(target.get("track_name"), 256) != _text(track_name, 256):
        errors.append("revision_brief target track name does not match the request")
    listener = brief.get("listener") if isinstance(brief.get("listener"), dict) else {}
    if _text(listener.get("verdict"), 32).lower() != "revise":
        errors.append("revision_brief listener verdict must be 'revise'")
    requested_changes = listener.get("requested_changes")
    if not isinstance(requested_changes, list) or len(requested_changes) > 5:
        errors.append("revision_brief requested_changes must contain at most 5 items")
        requested_changes = []
    try:
        comparison = _safe_comparison(brief.get("comparison")) if brief.get("comparison") is not None else None
    except ValueError as exc:
        errors.append(str(exc))
        comparison = None
    safe = {
        "schema": SCHEMA,
        "feedback_id": _text(brief.get("feedback_id"), 128),
        "session_id": _text(session_id, 128),
        "source_receipt_id": _text(brief.get("source_receipt_id"), 256),
        "listener": {
            "verdict": "revise",
            "rating": listener.get("rating"),
            "comment": _text(listener.get("comment"), 1000),
            "requested_changes": [_text(item, 256) for item in requested_changes[:5] if _text(item, 256)],
        },
        "baseline": brief.get("baseline") if isinstance(brief.get("baseline"), dict) else {},
        "comparison": comparison,
        "target": {
            "track_index": requested_track_index,
            "track_name": _text(track_name, 256),
            "clip_slot_index": requested_slot,
        },
        "advisory_only": True,
    }
    return safe, errors


__all__ = ["SCHEMA", "build_audition_revision_brief", "validate_revision_brief"]
