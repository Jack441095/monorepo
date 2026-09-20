"""Tests for business/app/routes/thursday_routes.py's status and
jarvis-action dispatch.

/api/thursday/status previously returned hardcoded "active_tasks": 0 and
"system_health": "100% operational" literals regardless of actual state --
nothing computed them. jarvis-action's explain_decisions/analyze_ableton/
audit_session actions called modules that no longer exist in the repo
(kenn_decision_explainer/kenn_daw_assistant/kenn_mix_doctor), raising an
unhandled ModuleNotFoundError for any direct API caller (the real UI in
thursday_hub.js only ever sends action "query", so this was unreachable
via normal use, but still crashed ungracefully if called directly).
"""

from __future__ import annotations

import json
import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "server" / "app") not in sys.path:
    sys.path.insert(0, str(ROOT / "server" / "app"))

from app.routes.thursday_routes import handle_thursday_get, handle_thursday_post  # noqa: E402


class FakeHandler:
    def __init__(self, body: dict | None = None) -> None:
        self._body = json.dumps(body or {}).encode("utf-8")
        self.headers = {"Content-Length": str(len(self._body))}
        self.rfile = BytesIO(self._body)
        self.status = 0
        self.payload: dict = {}

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload

    def read_json_body(self) -> dict:
        return json.loads(self._body.decode("utf-8"))


def test_status_route_does_not_claim_a_specific_task_count_or_health_score() -> None:
    handler = FakeHandler()
    handled = handle_thursday_get(handler, "/api/thursday/status")

    assert handled is True
    assert handler.status == 200
    assert handler.payload["ok"] is True
    assert handler.payload["status"] == "online"
    # The old bug: fixed literals nothing ever computed.
    assert "active_tasks" not in handler.payload
    assert "system_health" not in handler.payload


def test_dashboard_status_alias_matches_status() -> None:
    handler = FakeHandler()
    handled = handle_thursday_get(handler, "/api/thursday/dashboard-status")
    assert handled is True
    assert handler.status == 200
    assert handler.payload["ok"] is True


def test_jarvis_action_explain_decisions_fails_honestly_not_with_a_crash() -> None:
    handler = FakeHandler({"action": "explain_decisions", "mix_plan": {}})
    handled = handle_thursday_post(handler, "/api/thursday/jarvis-action")

    assert handled is True
    assert handler.status == 501
    assert handler.payload["ok"] is False
    assert handler.payload["action"] == "explain_decisions"


def test_jarvis_action_analyze_ableton_fails_honestly_not_with_a_crash() -> None:
    handler = FakeHandler({"action": "analyze_ableton", "track_name": "Vox"})
    handled = handle_thursday_post(handler, "/api/thursday/jarvis-action")

    assert handled is True
    assert handler.status == 501


def test_jarvis_action_audit_session_fails_honestly_not_with_a_crash() -> None:
    handler = FakeHandler({"action": "audit_session", "stems": {}})
    handled = handle_thursday_post(handler, "/api/thursday/jarvis-action")

    assert handled is True
    assert handler.status == 501


def test_autonomous_execute_route_fails_closed_not_fabricated_success() -> None:
    """Phase-0 P0-8 (docs/audits/2026-08-20-thursday-nitedsp-forensic-audit.md):
    /api/thursday/autonomous-execute previously returned a fabricated
    "4-stage pipeline completed" response with fake stem filenames that were
    never written to disk. It must now report NOT_IMPLEMENTED/PROTOTYPE_ONLY
    rather than claim audio work occurred."""
    handler = FakeHandler({
        "instruction": "Create a 90 BPM Lo-Fi beat with swing",
        "genre": "lofi",
        "bpm": 90,
    })
    handled = handle_thursday_post(handler, "/api/thursday/autonomous-execute")

    assert handled is True
    assert handler.status == 200
    assert handler.payload.get("ok") is False
    assert handler.payload.get("status") == "NOT_IMPLEMENTED"
    assert handler.payload.get("reason") == "PROTOTYPE_ONLY"
    assert "pipeline_steps" not in handler.payload
    assert "steps_completed" not in handler.payload
