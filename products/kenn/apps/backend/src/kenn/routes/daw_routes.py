"""Modular Ableton Live 12 DAW Control route handlers for KENN.

Handles:
- /api/ableton/command (two-way natural language commands & confirmations)
- /api/ableton/session-card (live track topology & device state)
- /api/ableton/osc/undo (two-phase verified inverse actions)
- /api/ableton/midi-clip/proposal
"""

from __future__ import annotations

from typing import Any

from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command
from kenn.core.midi_clip_service import MidiClipActionService
from kenn.core.action_policy import action_allowed, action_denied_message


def handle_live_command(
    payload: dict[str, Any],
    *,
    pending_proposals: dict[str, Any],
    session_id: str = "",
) -> tuple[int, dict[str, Any]]:
    """Execute or plan a natural language Ableton Live command."""
    sess_id = str(payload.get("session_id") or session_id or "").strip()
    command = str(payload.get("command") or payload.get("question") or "").strip()
    deterministic_only = bool(payload.get("deterministic_only", False))
    confirm_token = str(payload.get("confirm_token") or payload.get("confirmation_token") or "").strip()
    proposal = payload.get("proposal") if isinstance(payload.get("proposal"), dict) else None

    if proposal is None and confirm_token and confirm_token in pending_proposals:
        proposal = pending_proposals[confirm_token]

    if proposal is not None and not action_allowed("daw_control"):
        return 403, {"ok": False, "error": action_denied_message("daw_control")}

    result = handle_command(
        command,
        session_id=sess_id,
        proposal=proposal,
        confirm_token=confirm_token,
        idempotency_key=str(payload.get("idempotency_key", "")),
        llm_plan=payload.get("llm_plan") if isinstance(payload.get("llm_plan"), dict) else None,
        recipe_steps=payload.get("recipe_steps") if isinstance(payload.get("recipe_steps"), list) else None,
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
    elif result.get("status") == "failed":
        status = 409

    return status, result


def handle_session_card() -> tuple[int, dict[str, Any]]:
    """Return live Ableton session topology from resilient MixingDoctor cache."""
    try:
        from kenn.mixing_doctor import get_latest_session_state
        state = get_latest_session_state()
        if state and isinstance(state, dict):
            return 200, {"ok": True, "session": state}
        # Fallback to direct bridge query
        from kenn.ableton_osc_bridge import live_client
        direct_state = live_client.query_session_state()
        return 200, {"ok": True, "session": direct_state}
    except Exception as exc:
        return 200, {"ok": False, "status": "offline", "error": str(exc), "session": {"status": "offline", "tracks": []}}


def handle_osc_undo(
    payload: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Execute two-phase undo: Phase 1 proposes inverse; Phase 2 executes with token."""
    service = LiveActionService()
    session_id = str(payload.get("session_id", "")).strip()
    receipt = payload.get("receipt")

    if not session_id or not isinstance(receipt, dict):
        return 400, {"ok": False, "error": "session_id and a verified receipt are required for undo."}

    if "proposal" not in payload:
        result = service.propose_undo(receipt, session_id=session_id)
        return (200 if result.get("ok") else 409), result

    if not action_allowed("daw_control"):
        return 403, {"ok": False, "error": action_denied_message("daw_control")}

    undo_proposal = payload["proposal"]
    result = service.execute(
        undo_proposal,
        confirm_token=str(payload.get("confirm_token", "")),
        session_id=session_id,
        idempotency_key=str(payload.get("idempotency_key", "")),
    )
    return (200 if result.get("ok") else 409), result

