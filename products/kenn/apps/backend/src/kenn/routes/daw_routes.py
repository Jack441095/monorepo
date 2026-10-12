"""Modular Ableton Live 12 DAW Control route handlers for KENN.

Handles:
- /api/ableton/command (two-way natural language commands & confirmations)
- /api/ableton/session-card (live track topology & device state)
- /api/ableton/osc/undo (two-phase verified inverse actions)
- /api/ableton/midi-clip/proposal
"""

from __future__ import annotations

from typing import Any

from kenn.core.confirmation import revoke_confirmation


def handle_confirmation_revoke(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    session_id = payload.get("session_id")
    token = payload.get("confirm_token")
    if (
        not isinstance(session_id, str) or not session_id or len(session_id) > 128
        or session_id != session_id.strip()
        or not isinstance(token, str) or not token or len(token) > 512
    ):
        return 400, {"ok": False, "error": "An exact session_id and confirm_token are required."}
    if not revoke_confirmation(token, session_id=session_id):
        return 409, {
            "ok": False,
            "status": "not_revoked",
            "error": "This confirmation is no longer pending for this chat. It may be expired, dismissed, or already executing.",
        }
    return 200, {"ok": True, "status": "revoked"}


class _Reply:
    """Collects what the stdlib handler would have written so FastAPI can return it."""

    def __init__(self) -> None:
        self.status = 500
        self.body: dict[str, Any] = {"ok": False, "error": "The Live command produced no response."}

    def send_json(self, status: int, body: dict[str, Any]) -> None:
        self.status, self.body = status, body


def handle_live_command(
    payload: dict[str, Any],
    *,
    pending_proposals: dict[str, Any],
    session_id: str = "",
) -> tuple[int, dict[str, Any]]:
    """Run a Live command through the same handler the stdlib server uses.

    This used to be a second copy that sent every proposal to the generic planner, so a MIDI clip,
    duplication, rename, audition or sample proposal came back "requires confirmation" and was never
    applied, and a command that did apply recorded no receipt for Undo.
    """
    from kenn.routes.daw_command_handler import handle_live_command as stdlib_handle_live_command

    if session_id and not payload.get("session_id"):
        payload = {**payload, "session_id": session_id}
    reply = _Reply()
    stdlib_handle_live_command(reply, None, pending_proposals, payload)
    return reply.status, reply.body


def handle_parameter_inspection(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Expose current raw metadata through the same policy as the proposal gateway."""
    from kenn.core.action_policy import action_allowed, action_denied_message
    from kenn.core.live_action_service import LiveActionService

    if not action_allowed("daw_control"):
        return 403, {"ok": False, "error": action_denied_message("daw_control")}
    if not isinstance(payload, dict) or set(payload) != {"address", "parameter_index"}:
        return 400, {"ok": False, "error": "Supply address and parameter_index only."}
    result = LiveActionService().inspect_addressed_parameter(**payload)
    return (200 if result.get("success") else 409), {**result, "ok": bool(result.get("success")), "changed": False}


def handle_parameter_proposal(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Resolve a typed candidate without granting it execution or confirmation authority."""
    from kenn.core.action_policy import action_allowed, action_denied_message
    from kenn.core.live_action_service import LiveActionService

    if not action_allowed("daw_control"):
        return 403, {"ok": False, "error": action_denied_message("daw_control")}
    required = {"session_id", "address", "parameter_index", "parameter_name", "device_name", "value", "unit"}
    if not isinstance(payload, dict) or not required <= payload.keys() or payload.keys() - required - {"relative"}:
        return 400, {"ok": False, "error": "Supply exactly the typed parameter candidate fields."}
    for key in ("session_id", "parameter_name", "device_name", "unit"):
        value = payload[key]
        if not isinstance(value, str) or not value or value != value.strip() or len(value) > 128:
            return 400, {"ok": False, "error": f"An exact {key} is required."}
    if type(payload.get("relative", False)) is not bool or isinstance(payload["value"], bool):
        return 400, {"ok": False, "error": "relative must be boolean and value must be a number or choice label."}
    result = LiveActionService().propose_addressed_parameter_action(
        **{key: payload[key] for key in required}, relative=payload.get("relative", False),
    )
    if result.get("ok"):
        result.update({"changed": False, "status": "confirmation_required", "requires_confirmation": True})
    return (200 if result.get("ok") else 409), result


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
    """Two-phase undo through the stdlib owner, so FastAPI reverses the same receipts the stdlib server does."""
    from kenn.routes.daw_command_handler import handle_osc_undo as stdlib_handle_osc_undo

    reply = _Reply()
    stdlib_handle_osc_undo(reply, payload)
    return reply.status, reply.body
