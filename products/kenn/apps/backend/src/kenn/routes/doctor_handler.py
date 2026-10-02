"""KENN Route Handlers: Session Doctor & Surgical Masking Remediation."""

from __future__ import annotations

from typing import Any


# Only masking issues carry a conflict track and an EQ suggestion; the session doctor's Issue has none of them, so
# reading them straight off it made every audit that found something a 500 (seen from the app, 26 Sept 2026).
_OPTIONAL_ISSUE_FIELDS = ("conflict_track_index", "conflict_track_name", "frequency_hz", "gain_recommendation_db",
                          "q_recommendation")


def _issue_json(issue: Any) -> dict[str, Any]:
    row = {name: getattr(issue, name) for name in ("code", "severity", "track_index", "track_name", "description",
                                                   "suggested_action", "proposed_value")}
    row.update({name: getattr(issue, name) for name in _OPTIONAL_ISSUE_FIELDS if getattr(issue, name, None) is not None})
    return row


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
            "issues": [_issue_json(i) for i in report.issues],
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
            "issues": [_issue_json(i) for i in report.issues],
            "remediation_batch": report.remediation_batch,
        })
    except Exception as e:
        handler.send_json(500, {"ok": False, "error": str(e)})


def handle_post_doctor_remediate(handler: Any, payload: dict[str, Any]) -> None:
    """POST /api/session/doctor/remediate - disabled.

    The old body called SessionDoctor.formulate_surgical_remediation_proposal with arguments it does not take,
    so it always answered 500, and its confirmed branch said "applied" without writing anything to Live. It
    stays closed until remediation goes through the typed proposal service with a readback.
    """
    handler.send_json(410, {
        "ok": False,
        "error": "Session Doctor remediation is disabled until it has a typed, reversible proposal and verified readback.",
    })
