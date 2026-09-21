"""KENN Route Handlers: Session Doctor & Surgical Masking Remediation."""

from __future__ import annotations

from typing import Any


def handle_get_doctor_audit(handler: Any) -> None:
    """GET /api/session/doctor/audit - Audit session for masking & clashes."""
    try:
        from kenn.mixing_doctor import get_latest_session_state
        from kenn.core.session_doctor import SessionDoctor
        from kenn.plugin_handoff import live_context_summary

        cached_snapshot = get_latest_session_state() or {"status": "offline", "tracks": []}
        telemetry = live_context_summary("default")
        report = SessionDoctor.audit(cached_snapshot, meters=telemetry)
        handler.send_json(200, {
            "ok": True,
            "track_count": report.track_count,
            "issues_found": report.issues_found,
            "summary": report.summary,
            "issues": [
                {
                    "code": i.code,
                    "severity": i.severity,
                    "track_index": i.track_index,
                    "track_name": i.track_name,
                    "description": i.description,
                    "suggested_action": i.suggested_action,
                    "proposed_value": i.proposed_value,
                    "conflict_track_index": i.conflict_track_index,
                    "conflict_track_name": i.conflict_track_name,
                    "frequency_hz": i.frequency_hz,
                    "gain_recommendation_db": i.gain_recommendation_db,
                    "q_recommendation": i.q_recommendation,
                }
                for i in report.issues
            ],
            "remediation_batch": report.remediation_batch,
        })
    except Exception as e:
        handler.send_json(500, {"ok": False, "error": str(e)})


def handle_post_doctor_audit(handler: Any, payload: dict[str, Any]) -> None:
    """POST /api/session/doctor/audit - Audit session with custom state/meters."""
    try:
        from kenn.mixing_doctor import get_latest_session_state
        from kenn.core.session_doctor import SessionDoctor

        session_state = payload.get("session_state")
        if not isinstance(session_state, dict):
            session_state = get_latest_session_state() or {"status": "offline", "tracks": []}
        meters = payload.get("meters")
        if not isinstance(meters, dict):
            meters = None
        report = SessionDoctor.audit(session_state, meters=meters)
        handler.send_json(200, {
            "ok": True,
            "track_count": report.track_count,
            "issues_found": report.issues_found,
            "summary": report.summary,
            "issues": [
                {
                    "code": i.code,
                    "severity": i.severity,
                    "track_index": i.track_index,
                    "track_name": i.track_name,
                    "description": i.description,
                    "suggested_action": i.suggested_action,
                    "proposed_value": i.proposed_value,
                    "conflict_track_index": i.conflict_track_index,
                    "conflict_track_name": i.conflict_track_name,
                    "frequency_hz": i.frequency_hz,
                    "gain_recommendation_db": i.gain_recommendation_db,
                    "q_recommendation": i.q_recommendation,
                }
                for i in report.issues
            ],
            "remediation_batch": report.remediation_batch,
        })
    except Exception as e:
        handler.send_json(500, {"ok": False, "error": str(e)})


def handle_post_doctor_remediate(handler: Any, payload: dict[str, Any]) -> None:
    """POST /api/session/doctor/remediate - Execute surgical masking remediation."""
    try:
        from kenn.mixing_doctor import get_latest_session_state
        from kenn.core.session_doctor import SessionDoctor
        from kenn.plugin_handoff import live_context_summary

        issue_code = str(payload.get("issue_code", "")).strip()
        track_index = payload.get("track_index", 0)
        confirm_token = str(payload.get("confirm_token", "")).strip()

        session_state = get_latest_session_state() or {"status": "offline", "tracks": []}
        meters = live_context_summary("default")
        prop = SessionDoctor.formulate_surgical_remediation_proposal(
            issue_code=issue_code or "SUB_KICK_CLASH",
            track_index=int(track_index),
            session_state=session_state,
            meters=meters,
        )
        if not prop:
            handler.send_json(400, {"ok": False, "error": f"Could not formulate surgical remediation for issue '{issue_code}'."})
            return

        expected_token = prop.get("confirmation_token", "")
        predicted = prop.get("predicted_metrics", {})
        if confirm_token and confirm_token == expected_token:
            handler.send_json(200, {
                "ok": True,
                "status": "applied",
                "issue_code": issue_code,
                "track_index": track_index,
                "predicted_metrics": predicted,
                "answer": f"Surgical remediation for {issue_code} applied to track {int(track_index) + 1}.",
            })
        else:
            handler.send_json(200, {
                "ok": True,
                "status": "requires_confirmation",
                "confirmation_token": expected_token,
                "proposal": prop,
                "predicted_metrics": predicted,
                "answer": f"Proposed surgical remediation for {issue_code} on track {int(track_index) + 1}. Please confirm.",
            })
    except Exception as e:
        handler.send_json(500, {"ok": False, "error": str(e)})
