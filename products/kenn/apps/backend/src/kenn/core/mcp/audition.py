"""Audition proposals plus the feedback loop that drives revisions.

Every handler here was lifted verbatim out of ``KennMCPFacade._dispatch``.
``facade`` is the facade that called it, so the injected client, coordinator,
and stores stay the single owner of Live and of the task ledger.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kenn.core.audition_revision import build_audition_revision_brief

if TYPE_CHECKING:  # pragma: no cover - import cycle broken for type checking only
    from kenn.core.mcp_facade import KennMCPFacade


def create_clip_audition_proposal(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    track_name = str(args.get("track_name", "")).strip()[:256]
    if not session_id or not track_name:
        raise ValueError("session_id and track_name are required")
    result = facade.client.post(
        "/api/ableton/clip-audition/proposal",
        {
            "session_id": session_id,
            "track_index": args.get("track_index"),
            "track_name": track_name,
            "clip_slot_index": args.get("clip_slot_index"),
            "source_receipt_id": str(args.get("source_receipt_id", ""))[:256],
        },
    )
    if result.get("receipt") or result.get("changed") is True:
        raise RuntimeError("KENN returned a mutation from a clip audition proposal-only MCP call")
    return result


def create_clip_audition_from_receipt(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    receipt = args.get("receipt")
    if not session_id or not isinstance(receipt, dict):
        raise ValueError("session_id and receipt are required")
    if receipt.get("schema") != "kenn.ableton_midi_clip_receipt.v1" or receipt.get("status") != "applied" or receipt.get("verified") is not True:
        raise ValueError("receipt must be a verified applied MIDI clip receipt")
    target = receipt.get("target") if isinstance(receipt.get("target"), dict) else {}
    if any(key not in target for key in ("track_index", "track_name", "clip_slot_index")):
        raise ValueError("receipt does not contain a complete exact MIDI clip target")
    result = facade.client.post(
        "/api/ableton/clip-audition/proposal",
        {
            "session_id": session_id,
            "track_index": target["track_index"],
            "track_name": str(target["track_name"])[:256],
            "clip_slot_index": target["clip_slot_index"],
            "source_receipt_id": str(receipt.get("receipt_id", ""))[:256],
        },
    )
    if result.get("receipt") or result.get("changed") is True:
        raise RuntimeError("KENN returned a mutation from a receipt-derived audition proposal-only MCP call")
    return {**result, "source_receipt_id": str(receipt.get("receipt_id", ""))[:256]}


def record_audition_feedback(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    receipt = args.get("receipt")
    verdict = str(args.get("verdict", "")).strip()[:32]
    if not session_id or not isinstance(receipt, dict) or not verdict:
        raise ValueError("session_id, receipt, and verdict are required")
    result = facade.client.post(
        "/api/ableton/audition-feedback",
        {
            "session_id": session_id,
            "receipt": receipt,
            "verdict": verdict,
            "rating": args.get("rating"),
            "comment": str(args.get("comment", ""))[:1000],
            "requested_changes": args.get("requested_changes"),
        },
    )
    if result.get("receipt") or result.get("changed") is True:
        raise RuntimeError("KENN returned a mutation from an advisory audition-feedback call")
    return result


def audition_feedback(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    try:
        limit = int(args.get("limit", 20))
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer between 1 and 100") from None
    if not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    return facade.client.get(
        "/api/ableton/audition-feedback",
        {"session_id": session_id, "limit": limit},
    )


def create_audition_revision_brief(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    feedback_id = str(args.get("feedback_id", "")).strip()[:128]
    if not session_id or not feedback_id:
        raise ValueError("session_id and feedback_id are required")
    result = facade.client.get(
        "/api/ableton/audition-feedback",
        {"session_id": session_id, "limit": 100},
    )
    items = result.get("feedback", []) if isinstance(result, dict) else []
    feedback = next(
        (
            item for item in items
            if isinstance(item, dict) and str(item.get("feedback_id", "")) == feedback_id
        ),
        None,
    )
    if feedback is None:
        raise ValueError("feedback_id was not found in the requested session")
    return build_audition_revision_brief(feedback, comparison=args.get("comparison"))
