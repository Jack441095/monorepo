"""Business admin calendar POST routes.

Split out of admin_routes.py (kept under a strict line budget by
tests/test_architecture_boundaries.py::test_route_modules_remain_near_the_500_line_budget).
"""

from __future__ import annotations

import json
from collections.abc import Callable


def handle_admin_calendar_post(handler, path: str, *, log_event: Callable[[str, str, str], None]) -> bool:
    """Handle /api/admin/calendar* POST routes. Returns True if handled."""
    if path == "/api/admin/calendar":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        text = str(payload.get("text", "")).strip()
        when = str(payload.get("when", "")).strip()
        if not text or not when:
            handler.send_json(400, {"error": "text and when are required fields."})
            return True
        from thursday.scheduling import schedule_reminder
        from db import add_record
        try:
            msg = schedule_reminder(text, when, add_record=add_record)
            log_event("calendar_event_created", "admin", f"Created event: {text} due {when}")
            handler.send_json(200, {"ok": True, "message": msg})
        except Exception as exc:
            handler.send_json(500, {"error": str(exc)})
        return True

    if path == "/api/admin/calendar/acknowledge":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        event_id = str(payload.get("id", "")).strip()
        if not event_id:
            handler.send_json(400, {"error": "id is required."})
            return True
        from thursday.scheduling import acknowledge_reminder
        try:
            ok = acknowledge_reminder(event_id)
            if ok:
                log_event("calendar_event_completed", "admin", f"Completed event: {event_id}")
                handler.send_json(200, {"ok": True})
            else:
                handler.send_json(404, {"error": "Event not found."})
        except Exception as exc:
            handler.send_json(500, {"error": str(exc)})
        return True

    return False
