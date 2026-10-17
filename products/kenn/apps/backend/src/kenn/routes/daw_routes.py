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


def _offline_scan_session(payload: Any, allowed: set[str]) -> str | None:
    """Return the exact owner session when the payload carries only the allowed keys."""
    if not isinstance(payload, dict) or set(payload) != allowed:
        return None
    session_id = payload["session_id"]
    if not isinstance(session_id, str) or not session_id or session_id != session_id.strip() or len(session_id) > 128:
        return None
    return session_id


def handle_offline_scan_proposal(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Bind a producer-confirmed range to a single-use confirmation; nothing is exported yet."""
    from kenn.core.live_action_service import LiveActionService
    from kenn.core.offline_scan_runtime import get_offline_scan_service

    session_id = _offline_scan_session(payload, {"session_id", "source", "export_request"})
    if session_id is None or not isinstance(payload["source"], dict) or not isinstance(payload["export_request"], dict):
        return 400, {"ok": False, "error": "Supply exactly session_id, source and export_request."}
    result = LiveActionService(offline_scans=get_offline_scan_service()).propose_offline_scan(
        source=payload["source"], export_request=payload["export_request"], session_id=session_id,
    )
    if result.get("ok"):
        result.update({"changed": False, "status": "confirmation_required"})
    return (200 if result.get("ok") else 409), result


def handle_offline_scan_start(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Consume the confirmation and start the job; the 202 receipt is polled through status."""
    from kenn.core.live_action_service import LiveActionService
    from kenn.core.offline_scan_runtime import get_offline_scan_service

    session_id = _offline_scan_session(payload, {"session_id", "proposal", "confirm_token", "idempotency_key"})
    if (
        session_id is None or not isinstance(payload["proposal"], dict)
        or not isinstance(payload["confirm_token"], str) or len(payload["confirm_token"]) > 512
    ):
        return 400, {"ok": False, "error": "Supply exactly session_id, proposal, confirm_token and idempotency_key."}
    result = LiveActionService(offline_scans=get_offline_scan_service(before_start=True)).execute_offline_scan(
        payload["proposal"], confirm_token=payload["confirm_token"], session_id=session_id,
        idempotency_key=payload["idempotency_key"],
    )
    return (202 if result.get("ok") else 409), result


def _offline_scan_job_call(payload: dict[str, Any], method: str) -> tuple[int, dict[str, Any]]:
    from kenn.core.offline_scan_runtime import get_offline_scan_service

    session_id = _offline_scan_session(payload, {"session_id", "job_id"})
    if session_id is None or not isinstance(payload["job_id"], str) or len(payload["job_id"]) > 128:
        return 400, {"ok": False, "error": "Supply exactly session_id and job_id."}
    service = get_offline_scan_service()
    if service is None:
        # Nothing can have been started without a service, so there is no job to read or cancel.
        return 409, {"ok": False, "error": "No qualified offline export candidate is configured."}
    result = getattr(service, method)(session_id, payload["job_id"])
    # The service answers a missing, invalid and foreign job identically, so 404 leaks nothing about ownership.
    return (200 if result.get("ok") else 404), result


def handle_offline_scan_status(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Return this owner's job receipt, including the retained report once completed."""
    return _offline_scan_job_call(payload, "status")


def handle_offline_scan_cancel(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Request cancellation of this owner's job; the receipt shows when disposal finished."""
    return _offline_scan_job_call(payload, "cancel")


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


def handle_session_tracks() -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/session-tracks."""
    import os
    from kenn.core.ableton_project_detector import detect_active_ableton_project, find_project_bounces
    from kenn.core.track_diagnostic import extract_session_tracks, build_tracks_from_live_session
    from kenn.mixing_doctor import get_latest_session_state

    proj = detect_active_ableton_project() or {"project_name": "Untitled", "project_dir": "", "als_path": ""}
    session = get_latest_session_state()
    bounces = find_project_bounces(proj["project_dir"]) if proj.get("project_dir") else []

    if session.get("status") == "connected" and session.get("tracks"):
        tracks = build_tracks_from_live_session(session["tracks"], bounces)
    elif proj.get("als_path") and os.path.isfile(proj["als_path"]):
        tracks = extract_session_tracks(proj["als_path"], proj["project_dir"])
    else:
        tracks = []

    return 200, {
        "ok": True,
        "project_name": proj["project_name"],
        "project_dir": proj["project_dir"],
        "tracks": tracks,
    }


def handle_project_audio_poll(since_raw: str = "0") -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/project-audio/poll.

    Ableton Live writes rendered WAVs directly to disk on export (Cmd+Shift+R)
    without firing an OSC notification. We poll filesystem modified timestamps
    so the frontend can offer one-click hydration the moment an export lands.
    """
    from kenn.core.ableton_project_detector import detect_active_ableton_project, find_project_bounces

    try:
        since = float(since_raw.strip())
    except (TypeError, ValueError):
        since = 0.0

    proj = detect_active_ableton_project()
    if not proj:
        return 200, {
            "ok": False,
            "has_new": False,
            "error": "No active Ableton Live project detected.",
            "latest_mtime": since,
        }

    bounces = find_project_bounces(proj["project_dir"])
    if not bounces:
        return 200, {"ok": True, "has_new": False, "latest_mtime": since, "new_bounce": None}

    newest = max(bounces, key=lambda b: b.get("modified_time", 0.0))
    newest_mtime = float(newest.get("modified_time", 0.0))

    # When since == 0.0 (initial client mount), we establish baseline latest_mtime
    # without triggering an alert for historical bounces. A 1 ms threshold prevents
    # floating-point jitter from falsely re-triggering the same file.
    has_new = bool(since > 0.0 and newest_mtime > (since + 0.001))

    return 200, {
        "ok": True,
        "has_new": has_new,
        "latest_mtime": newest_mtime,
        "new_bounce": newest if has_new else None,
    }


def handle_project_audio_file(file_path: str) -> tuple[int, bytes | dict[str, Any], str]:
    """Return (status_code, content_or_error_dict, content_type) for /api/ableton/project-audio/file."""
    import os

    path_clean = file_path.strip()
    if not path_clean or not os.path.isfile(path_clean):
        return 404, {"ok": False, "error": "Audio file not found."}, "application/json"
    if not path_clean.lower().endswith((".wav", ".aif", ".aiff")):
        return 400, {"ok": False, "error": "Requested file is not an audio file."}, "application/json"
    try:
        with open(path_clean, "rb") as f:
            content = f.read()
        mime = "audio/aiff" if path_clean.lower().endswith((".aif", ".aiff")) else "audio/wav"
        return 200, content, mime
    except Exception as exc:
        return 500, {"ok": False, "error": f"Failed to read audio file: {exc}"}, "application/json"


def handle_midi_clip_proposal(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/midi-clip/proposal."""
    from kenn.core.midi_clip_action_service import MidiClipActionService

    session_id = str(payload.get("session_id", "")).strip()
    if not session_id:
        return 400, {"ok": False, "error": "session_id is required."}
    try:
        result = MidiClipActionService().propose_create(
            track_index=payload.get("track_index"),
            track_name=str(payload.get("track_name", "")),
            clip_slot_index=payload.get("clip_slot_index"),
            length=payload.get("length"),
            notes=payload.get("notes"),
            session_id=session_id,
            source_artifact_sha256=str(payload.get("source_artifact_sha256", "")),
            source_artifact_id=str(payload.get("source_artifact_id", "")),
        )
    except (TypeError, ValueError) as exc:
        return 400, {"ok": False, "error": str(exc)}
    return (200 if result.get("ok") else 409), result


def handle_midi_clip_update_proposal(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/midi-clip/update-proposal."""
    from kenn.core.midi_clip_action_service import MidiClipActionService

    session_id = str(payload.get("session_id", "")).strip()
    if not session_id:
        return 400, {"ok": False, "error": "session_id is required."}
    try:
        result = MidiClipActionService().propose_update(
            track_index=payload.get("track_index"),
            track_name=str(payload.get("track_name", "")),
            clip_slot_index=payload.get("clip_slot_index"),
            notes=payload.get("notes"),
            session_id=session_id,
            source_receipt_id=str(payload.get("source_receipt_id", "")),
        )
    except (TypeError, ValueError) as exc:
        return 400, {"ok": False, "error": str(exc)}
    if result.get("receipt") or result.get("changed") is True:
        return 500, {"ok": False, "error": "MIDI clip update proposal endpoint returned a mutation."}
    return (200 if result.get("ok") else 409), result


def handle_clip_duplication_proposal(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/clip-duplication/proposal."""
    from kenn.core.clip_duplication_action_service import ClipDuplicationActionService

    session_id = str(payload.get("session_id", "")).strip()
    if not session_id:
        return 400, {"ok": False, "error": "session_id is required."}
    try:
        result = ClipDuplicationActionService().propose(
            source_track_index=payload.get("source_track_index"),
            source_track_name=str(payload.get("source_track_name", "")),
            source_clip_slot_index=payload.get("source_clip_slot_index"),
            target_track_index=payload.get("target_track_index"),
            target_track_name=str(payload.get("target_track_name", "")),
            target_clip_slot_index=payload.get("target_clip_slot_index"),
            session_id=session_id,
        )
    except (TypeError, ValueError) as exc:
        return 400, {"ok": False, "error": str(exc)}
    if result.get("receipt") or result.get("changed") is True:
        return 500, {"ok": False, "error": "Clip duplication proposal endpoint returned a mutation."}
    return (200 if result.get("ok") else 409), result


def handle_clip_rename_proposal(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/clip-rename/proposal."""
    from kenn.core.clip_rename_action_service import ClipRenameActionService

    session_id = str(payload.get("session_id", "")).strip()
    if not session_id:
        return 400, {"ok": False, "error": "session_id is required."}
    try:
        result = ClipRenameActionService().propose(
            track_index=payload.get("track_index"),
            track_name=str(payload.get("track_name", "")),
            clip_slot_index=payload.get("clip_slot_index"),
            new_name=str(payload.get("new_name", "")),
            session_id=session_id,
        )
    except (TypeError, ValueError) as exc:
        return 400, {"ok": False, "error": str(exc)}
    if result.get("receipt") or result.get("changed") is True:
        return 500, {"ok": False, "error": "Clip rename proposal endpoint returned a mutation."}
    return (200 if result.get("ok") else 409), result


def handle_sample_import_proposal(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/sample-import/proposal."""
    from kenn.core.sample_import_service import SampleImportService

    session_id = str(payload.get("session_id", "")).strip()
    if not session_id:
        return 400, {"ok": False, "error": "session_id is required."}
    try:
        result = SampleImportService().propose_import(
            track_index=payload.get("track_index"),
            track_name=str(payload.get("track_name", "")),
            clip_slot_index=payload.get("clip_slot_index"),
            sample_id=str(payload.get("sample_id", "")),
            session_id=session_id,
        )
    except (TypeError, ValueError) as exc:
        return 400, {"ok": False, "error": str(exc)}
    return (200 if result.get("ok") else 409), result


def handle_clip_audition_proposal(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/clip-audition/proposal."""
    from kenn.core.clip_audition_action_service import ClipAuditionActionService

    session_id = str(payload.get("session_id", "")).strip()
    if not session_id:
        return 400, {"ok": False, "error": "session_id is required."}
    try:
        result = ClipAuditionActionService().propose(
            track_index=payload.get("track_index"),
            track_name=str(payload.get("track_name", "")),
            clip_slot_index=payload.get("clip_slot_index"),
            session_id=session_id,
            source_receipt_id=str(payload.get("source_receipt_id", "")),
        )
    except (TypeError, ValueError) as exc:
        return 400, {"ok": False, "error": str(exc)}
    return (200 if result.get("ok") else 409), result


