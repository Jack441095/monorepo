"""DAW Command & Live Action Routes.

Handles HTTP-level Live mutations, proposal execution, and the command gateway.
"""

from __future__ import annotations

import sys
import time
from typing import Any

import kenn.core.live_action_service as live_action_service_module
import kenn.core.live_command as live_command_module
from kenn.core.action_policy import action_allowed, action_denied_message
from kenn.core.live_receipt_journal import record_receipt
from kenn.core.midi_clip_service import (
    CREATE_PROPOSAL_SCHEMA,
    MidiClipActionService,
    UPDATE_PROPOSAL_SCHEMA,
)
from kenn.core.clip_duplication_service import (
    ClipDuplicationActionService,
    PROPOSAL_SCHEMA as CLIP_DUPLICATION_PROPOSAL_SCHEMA,
)
from kenn.core.clip_rename_service import (
    ClipRenameActionService,
    PROPOSAL_SCHEMA as CLIP_RENAME_PROPOSAL_SCHEMA,
)
from kenn.core.clip_audition_service import (
    ClipAuditionActionService,
    PROPOSAL_SCHEMA as CLIP_AUDITION_PROPOSAL_SCHEMA,
)
from kenn.core.sample_import_service import (
    IMPORT_PROPOSAL_SCHEMA as SAMPLE_IMPORT_PROPOSAL_SCHEMA,
    REMOVE_PROPOSAL_SCHEMA as SAMPLE_IMPORT_REMOVE_PROPOSAL_SCHEMA,
    SampleImportService,
)


def _get_live_action_service():
    server_mod = sys.modules.get("kenn.server")
    if server_mod and hasattr(server_mod, "LiveActionService"):
        return getattr(server_mod, "LiveActionService")
    return live_action_service_module.LiveActionService


def _get_handle_command():
    server_mod = sys.modules.get("kenn.server")
    if server_mod and hasattr(server_mod, "handle_command"):
        return getattr(server_mod, "handle_command")
    return live_command_module.handle_command


def handle_safe_live_action(handler: Any, action: str, payload: dict) -> None:
    """Handle the only supported HTTP Live mutation path."""
    service_cls = _get_live_action_service()
    service = service_cls()
    session_id = str(payload.get("session_id", "")).strip()
    if not session_id:
        handler.send_json(400, {"ok": False, "error": "session_id is required."})
        return
    proposal = payload.get("proposal")
    if proposal is None:
        try:
            if action in {"set_volume", "set_pan", "set_mute", "set_solo", "set_arm"}:
                if "track_index" not in payload:
                    handler.send_json(400, {"ok": False, "error": "track_index is required; KENN never assumes track 0."})
                    return
                fields = {
                    "set_volume": "volume",
                    "set_pan": "pan",
                    "set_mute": "muted",
                    "set_solo": "soloed",
                    "set_arm": "armed",
                }
                value_key = fields[action]
                if value_key not in payload:
                    handler.send_json(400, {"ok": False, "error": f"{value_key} is required."})
                    return
                result = service.propose_track_action(
                    action,
                    track_index=int(payload["track_index"]),
                    track_name=str(payload.get("track_name", "")),
                    value=payload[value_key],
                    session_id=session_id,
                )
            elif action in {"transport_play", "transport_stop"}:
                result = service.propose_transport_action(action, session_id=session_id)
            else:
                handler.send_json(410, {"ok": False, "error": f"Live action is disabled: {action}."})
                return
        except (TypeError, ValueError) as exc:
            handler.send_json(400, {"ok": False, "error": str(exc)})
            return
        handler.send_json(200 if result.get("ok") else 409, result)
        return

    if not action_allowed("daw_control"):
        handler.send_json(403, {"ok": False, "error": action_denied_message("daw_control")})
        return
    confirm_token = str(payload.get("confirm_token", ""))
    result = service.execute(
        proposal,
        confirm_token=confirm_token,
        session_id=session_id,
        idempotency_key=str(payload.get("idempotency_key", "")),
        correlation_id=str(payload.get("correlation_id", "")),
    )
    if isinstance(result.get("receipt"), dict):
        record_receipt(result["receipt"], session_id=session_id)
    handler.send_json(200 if result.get("ok") else 409, result)


def handle_live_command(handler: Any, mix_review: Any, pending_proposals: dict, payload: dict) -> None:
    """Plan or execute a user-facing, LLM-compatible Live command."""
    session_id = str(payload.get("session_id", "")).strip()
    command = str(payload.get("command") or payload.get("question") or "").strip()
    deterministic_only = bool(payload.get("deterministic_only", False))
    confirm_token = str(payload.get("confirm_token") or payload.get("confirmation_token") or "").strip()
    proposal = payload.get("proposal") if isinstance(payload.get("proposal"), dict) else None
    if proposal is None and confirm_token and confirm_token in pending_proposals:
        proposal = pending_proposals[confirm_token]
    source_evidence = None
    recipe_steps = payload.get("recipe_steps") if isinstance(payload.get("recipe_steps"), list) else None
    mix_review_id = str(payload.get("mix_review_id", "")).strip()[:128]
    if recipe_steps is not None and mix_review_id and proposal is None:
        if not mix_review:
            handler.send_json(503, {"ok": False, "error": "Mix Review evidence is unavailable; no evidence-bound recipe was created."})
            return
        try:
            review_result = mix_review.mix_review_status(mix_review_id)
            review = review_result.get("review") if isinstance(review_result, dict) else None
            if not isinstance(review, dict):
                handler.send_json(409, {"ok": False, "error": "The requested Mix Review was not found or has no measured review record."})
                return
            review_status = str(review.get("status", review_result.get("status", ""))).strip().lower()
            if review_status not in {"completed", "complete", "success", "approved", "ready"}:
                handler.send_json(409, {"ok": False, "error": f"Mix Review is not complete (status: {review_status or 'unknown'}); no evidence-bound recipe was created."})
                return
            from kenn.project_analysis import recommendations_from_mix_review

            source_evidence = {
                "schema": "kenn.mix_review_evidence.v1",
                "review_id": mix_review_id,
                "status": review.get("status", review_result.get("status", "unknown")),
                "source_scope": "uploaded_or_rendered_audio",
                "live_target_inference_allowed": False,
                "recommendations": [
                    item.payload() for item in recommendations_from_mix_review(review)
                ],
            }
        except Exception as exc:
            handler.send_json(409, {"ok": False, "error": f"Mix Review evidence could not be loaded; no recipe was created: {exc}"})
            return
    if proposal is not None and not action_allowed("daw_control"):
        handler.send_json(403, {"ok": False, "error": action_denied_message("daw_control")})
        return
    if proposal and proposal.get("schema") in {CREATE_PROPOSAL_SCHEMA, UPDATE_PROPOSAL_SCHEMA}:
        midi_service = MidiClipActionService()
        execute = midi_service.execute_update if proposal.get("schema") == UPDATE_PROPOSAL_SCHEMA else midi_service.execute_create
        result = execute(
            proposal,
            confirm_token=str(payload.get("confirm_token", "")),
            session_id=session_id,
            idempotency_key=str(payload.get("idempotency_key", "")),
            correlation_id=str(payload.get("correlation_id", "")),
        )
        if isinstance(result.get("receipt"), dict):
            record_receipt(result["receipt"], session_id=session_id)
            if proposal.get("schema") == CREATE_PROPOSAL_SCHEMA and result.get("ok") and result["receipt"].get("verified"):
                target = result["receipt"].get("target") or {}
                result["next_actions"] = [{
                    "tool": "create_clip_audition_proposal",
                    "description": "Prepare a confirmation-only audition of the verified MIDI clip.",
                    "arguments": {
                        "session_id": session_id,
                        "track_index": target.get("track_index"),
                        "track_name": target.get("track_name", ""),
                        "clip_slot_index": target.get("clip_slot_index"),
                        "source_receipt_id": result["receipt"].get("receipt_id", ""),
                    },
                }]
        handler.send_json(200 if result.get("ok") else 409, result)
        return
    if proposal and proposal.get("schema") == CLIP_DUPLICATION_PROPOSAL_SCHEMA:
        result = ClipDuplicationActionService().execute(
            proposal,
            confirm_token=str(payload.get("confirm_token", "")),
            session_id=session_id,
            idempotency_key=str(payload.get("idempotency_key", "")),
            correlation_id=str(payload.get("correlation_id", "")),
        )
        if isinstance(result.get("receipt"), dict):
            record_receipt(result["receipt"], session_id=session_id)
        handler.send_json(200 if result.get("ok") else 409, result)
        return
    if proposal and proposal.get("schema") == CLIP_RENAME_PROPOSAL_SCHEMA:
        result = ClipRenameActionService().execute(
            proposal,
            confirm_token=str(payload.get("confirm_token", "")),
            session_id=session_id,
            idempotency_key=str(payload.get("idempotency_key", "")),
            correlation_id=str(payload.get("correlation_id", "")),
        )
        if isinstance(result.get("receipt"), dict):
            record_receipt(result["receipt"], session_id=session_id)
        handler.send_json(200 if result.get("ok") else 409, result)
        return
    if proposal and proposal.get("schema") == CLIP_AUDITION_PROPOSAL_SCHEMA:
        service = ClipAuditionActionService()
        if proposal.get("action") == "stop_clip":
            result = service.execute_stop(
                proposal,
                confirm_token=str(payload.get("confirm_token", "")),
                session_id=session_id,
                idempotency_key=str(payload.get("idempotency_key", "")),
                correlation_id=str(payload.get("correlation_id", "")),
            )
        else:
            result = service.execute(
                proposal,
                confirm_token=str(payload.get("confirm_token", "")),
                session_id=session_id,
                idempotency_key=str(payload.get("idempotency_key", "")),
                correlation_id=str(payload.get("correlation_id", "")),
            )
        if isinstance(result.get("receipt"), dict):
            record_receipt(result["receipt"], session_id=session_id)
        handler.send_json(200 if result.get("ok") else 409, result)
        return
    if proposal and proposal.get("schema") == SAMPLE_IMPORT_PROPOSAL_SCHEMA:
        result = SampleImportService().execute_import(
            proposal,
            confirm_token=str(payload.get("confirm_token", "")),
            session_id=session_id,
            idempotency_key=str(payload.get("idempotency_key", "")),
            correlation_id=str(payload.get("correlation_id", "")),
        )
        if isinstance(result.get("receipt"), dict):
            record_receipt(result["receipt"], session_id=session_id)
        handler.send_json(200 if result.get("ok") else 409, result)
        return
    if proposal and proposal.get("schema") == SAMPLE_IMPORT_REMOVE_PROPOSAL_SCHEMA:
        result = SampleImportService().execute_remove(
            proposal,
            confirm_token=str(payload.get("confirm_token", "")),
            session_id=session_id,
            idempotency_key=str(payload.get("idempotency_key", "")),
            correlation_id=str(payload.get("correlation_id", "")),
        )
        if isinstance(result.get("receipt"), dict):
            record_receipt(result["receipt"], session_id=session_id)
        handler.send_json(200 if result.get("ok") else 409, result)
        return
    handle_cmd = _get_handle_command()
    result = handle_cmd(
        command,
        session_id=session_id,
        proposal=proposal,
        confirm_token=str(payload.get("confirm_token", "")),
        idempotency_key=str(payload.get("idempotency_key", "")),
        llm_plan=payload.get("llm_plan") if isinstance(payload.get("llm_plan"), dict) else None,
        recipe_steps=recipe_steps,
        source_evidence=source_evidence,
        allow_llm=not deterministic_only,
    )
    if isinstance(result.get("proposal"), dict):
        prop = result["proposal"]
        tok = str(prop.get("confirmation_token", "")).strip()
        if tok:
            pending_proposals[tok] = prop
    status = 200
    if result.get("status") == "invalid":
        status = 400
    elif result.get("status") == "requires_confirmation":
        status = 200
    elif result.get("status") == "failed":
        status = 409
    if isinstance(result.get("receipt"), dict):
        record_receipt(result["receipt"], session_id=session_id)
    handler.send_json(status, result)
