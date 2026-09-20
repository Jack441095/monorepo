"""KENN Chat Context & Audio Evidence Enrichment.

Extracts measured plugin snapshots, stem masking, audio classification,
stored mix reviews, and cached Ableton Live session context into typed evidence
packets admitted to conversational history.
"""

from __future__ import annotations

from typing import Any

from kenn.core.evidence import (
    history_turn as evidence_history_turn,
    from_audio_classification_context,
    from_mix_review_context,
    from_plugin_context,
    from_stem_masking_context,
)
from kenn.plugin_handoff import live_context_summary

try:
    from audio_analysis.mix_review import mix_review
except ImportError:
    try:
        from kenn.core.local_mix_review_service import local_mix_review as mix_review
    except Exception:
        mix_review = None


def plugin_live_context_turn(session_id: str, context: dict | None = None) -> dict | None:
    """Expose a measured plug-in snapshot to KENN as explicit context."""
    context = live_context_summary(session_id) if context is None else context
    if not context:
        return None
    packet = from_plugin_context(context)
    return evidence_history_turn(packet) if packet else None


def stem_masking_context_turn(context: dict | None) -> dict | None:
    """Expose one validated stem-masking result to the answer layer."""
    packet = from_stem_masking_context(context)
    return evidence_history_turn(packet) if packet else None


def attach_stem_masking_evidence(payload: dict, context: dict | None) -> dict:
    """Return a metadata-only copy of validated masking evidence."""
    packet = from_stem_masking_context(context)
    if packet is not None:
        payload["stem_masking_evidence"] = packet.payload()
    return payload


def audio_classification_context_turn(context: dict | None) -> dict | None:
    """Expose one validated completed classifier result to answer history."""
    packet = from_audio_classification_context(context)
    return evidence_history_turn(packet) if packet else None


def attach_audio_classification_evidence(payload: dict, context: dict | None) -> dict:
    """Return metadata-only validated classifier evidence."""
    packet = from_audio_classification_context(context)
    if packet is not None:
        payload["audio_classification_evidence"] = packet.payload()
    return payload


def stored_mix_review_evidence(review_id: str) -> tuple[dict | None, Any | None]:
    """Load one bounded local Mix Review record and its typed evidence packet."""
    key = str(review_id or "").strip()[:128]
    if not key or not mix_review or not hasattr(mix_review, "mix_review_status"):
        return None, None
    try:
        result = mix_review.mix_review_status(key)
        review = result.get("review") if isinstance(result, dict) else None
        if not isinstance(review, dict):
            return None, None
        handoff = {
            "schema": "kenn_mix_review_handoff.v1",
            "metrics": review.get("metrics", {}),
            "reference_comparison": review.get("reference_comparison"),
        }
        packet = from_mix_review_context(handoff)
        return review, packet
    except Exception:
        return None, None


def attach_explicit_audio_evidence(
    payload: dict,
    *,
    review_id: str,
    plugin_session_id: str,
    review: dict | None,
    mix_evidence: Any | None,
    plugin_context: dict | None,
) -> dict:
    """Attach bounded optional evidence to chat metadata without mutation authority."""
    if not isinstance(review, dict) or mix_evidence is None:
        return payload
    payload["mix_review_evidence"] = {
        **mix_evidence.payload(),
        "review_id": str(review_id)[:128],
        "status": str(review.get("status") or "unknown")[:32],
    }
    if isinstance(plugin_context, dict) and plugin_session_id:
        from kenn.core.realtime_mix_comparison import build_realtime_mix_comparison

        payload["realtime_mix_comparison"] = build_realtime_mix_comparison(
            review,
            plugin_context,
            review_id=review_id,
            plugin_session_id=plugin_session_id,
        )
    return payload


def ableton_session_context_turn(include_ableton_context: object) -> dict | None:
    """Return a typed cached Ableton snapshot only when the user opts in."""
    if include_ableton_context is not True:
        return None
    try:
        from kenn.mixing_doctor import get_latest_session_state
        from kenn.core.evidence import from_ableton_session

        packet = from_ableton_session(get_latest_session_state())
    except Exception:
        return None
    return evidence_history_turn(packet) if packet else None
