"""Read-only Ableton/KENN dashboard routes."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import ableton_bridge
import llm_improvement
import lm_gaps
import tips_queries


def handle_ableton_get(handler, full_path: str) -> bool:
    """Handle authenticated Ableton/KENN dashboard reads."""
    parsed = urlparse("https://host" + full_path)
    path = parsed.path

    if path == "/api/activity":
        limit = handler.query_limit(parsed)
        handler.send_json(200, {"events": handler.list_events(limit)})
        return True
    if path == "/api/ableton/suggest":
        query = parse_qs(parsed.query).get("q", [""])[0]
        try:
            limit = int(parse_qs(parsed.query).get("limit", ["8"])[0])
        except ValueError:
            limit = 8
        handler.send_json(
            200,
            ableton_bridge.suggest_questions(query, limit=limit, include_dashboard_extra=True),
        )
        return True
    if path == "/api/ableton/transcripts":
        handler.send_json(200, {"items": ableton_bridge.list_transcript_items()})
        return True
    if path == "/api/ableton/notes":
        params = parse_qs(parsed.query)
        handler.send_json(
            200,
            {
                "items": ableton_bridge.list_notes(
                    status=params.get("status", [""])[0],
                    query=params.get("q", [""])[0],
                    limit=handler.query_limit(parsed, default=300),
                )
            },
        )
        return True
    if path == "/api/ableton/web-health":
        handler.send_json(200, ableton_bridge.web_health())
        return True
    if path == "/api/ableton/llm-status":
        handler.send_json(200, ableton_bridge.llm_status())
        return True
    if path == "/api/ableton/gaps":
        handler.send_json(
            200,
            {
                "summary": lm_gaps.summary(),
                "items": lm_gaps.list_gaps_filtered(status="open"),
                "drafted": lm_gaps.list_gaps_filtered(status="drafted"),
            },
        )
        return True
    if path == "/api/ableton/queries":
        handler.send_json(200, {"items": tips_queries.list_queries()})
        return True
    if path == "/api/ableton/suggested-notes":
        import suggested_notes_ops

        handler.send_json(200, {"items": suggested_notes_ops.list_suggested_notes()})
        return True
    if path == "/api/ableton/improvement":
        handler.send_json(200, llm_improvement.snapshot())
        return True
    if path == "/api/ableton/training-records":
        handler.send_json(
            200,
            llm_improvement.training_records_snapshot(limit=handler.query_limit(parsed, default=80)),
        )
        return True
    if path == "/api/ableton/mix-versions":
        session_id = str(parse_qs(parsed.query).get("session_id", [""])[0]).strip()
        if session_id:
            handler.send_json(200, ableton_bridge.list_mix_versions(session_id))
        else:
            handler.send_json(400, {"ok": False, "error": "Missing session_id query param"})
        return True
    if path == "/api/ableton/web-pack":
        handler.send_json(200, {"items": ableton_bridge.list_web_pack()})
        return True
    if path == "/api/ableton/note":
        name = parse_qs(parsed.query).get("name", [""])[0]
        if not name:
            handler.send_json(400, {"error": "name query parameter is required."})
            return True
        try:
            handler.send_json(200, ableton_bridge.read_note(name))
        except FileNotFoundError as exc:
            handler.send_json(404, {"error": str(exc)})
        return True
    # Live OSC session state now served by the KENN app itself
    # (studio/kenn/kenn/server.py) — see docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md.
    return False
