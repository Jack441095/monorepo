"""Creative Lab and AudioGen GET/POST routes."""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

import audiogen_bridge
import creative_lab


def handle_creative_lab_get(handler, parsed_path: str) -> bool:
    """Handle Creative Lab and AudioGen GET routes. Returns True if handled."""
    parsed = urlparse("https://host" + parsed_path)
    path = parsed.path

    if path == "/api/audiogen/status":
        handler.send_json(200, audiogen_bridge.status())
        return True

    if path == "/api/admin/audiogen/render-jobs":
        try:
            limit = int(parse_qs(parsed.query).get("limit", ["12"])[0])
        except ValueError:
            limit = 12
        handler.send_json(200, {"ok": True, "queue": audiogen_bridge.render_queue_snapshot(limit=limit)})
        return True

    if path == "/api/admin/audiogen/history":
        try:
            limit = int(parse_qs(parsed.query).get("limit", ["25"])[0])
        except ValueError:
            limit = 25
        handler.send_json(200, {"ok": True, "items": audiogen_bridge.list_render_history(limit=limit)})
        return True

    if path == "/api/admin/audiogen/render-job":
        job_id = parse_qs(parsed.query).get("id", [""])[0]
        result = audiogen_bridge.render_job(job_id)
        handler.send_json(200 if result.get("ok") else 404, result)
        return True

    if path == "/api/admin/audiogen/render-job/events":
        # Additive, read-only: no route previously exposed the
        # audiogen_job_events log over HTTP even though it's been captured
        # since migration 007. Backs the AudioGen UI's "generation trace"
        # panel. Calls audiogen_bridge.render_job_events(), which itself is
        # a thin wrapper over the existing audiogen_job_store.events()
        # reader -- no new write path, schema change, or change to any
        # other endpoint's behavior.
        job_id = parse_qs(parsed.query).get("id", [""])[0]
        result = audiogen_bridge.render_job_events(job_id)
        handler.send_json(200 if result.get("ok") else 404, result)
        return True

    if path == "/api/admin/creative-lab/sessions":
        try:
            limit = int(parse_qs(parsed.query).get("limit", ["20"])[0])
        except ValueError:
            limit = 20
        handler.send_json(200, creative_lab.snapshot(limit=limit))
        return True

    if path == "/api/admin/creative-lab/session":
        session_id = parse_qs(parsed.query).get("id", [""])[0]
        result = creative_lab.session_replay(session_id)
        handler.send_json(200 if result.get("ok") else 404, result)
        return True

    if path == "/api/admin/creative-lab/repair/comparison":
        feedback_id = parse_qs(parsed.query).get("id", [""])[0]
        result = creative_lab.repair_comparison(feedback_id)
        handler.send_json(200 if result.get("ok") else 404, result)
        return True

    if path == "/api/admin/creative-lab/repair/training-records":
        try:
            limit = int(parse_qs(parsed.query).get("limit", ["25"])[0])
        except ValueError:
            limit = 25
        handler.send_json(200, creative_lab.repair_training_export_snapshot(limit=limit))
        return True

    return False


def handle_creative_lab_post(handler, parsed_path: str, *, log_event: Callable[[str, str, str], None]) -> bool:
    """Handle Creative Lab and AudioGen POST routes. Returns True if handled."""
    parsed = urlparse("https://host" + parsed_path)
    path = parsed.path

    if path == "/api/admin/audiogen/generate":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        prompt = str(payload.get("prompt", "")).strip()
        if not prompt:
            handler.send_json(400, {"error": "prompt is required."})
            return True
        try:
            bars = int(payload.get("bars", 8) or 8)
        except (TypeError, ValueError):
            handler.send_json(400, {"error": "bars must be an integer."})
            return True
        result = audiogen_bridge.generate_for_kenn(
            prompt,
            emotion=str(payload.get("emotion", "")).strip(),
            bars=bars,
            publish=bool(payload.get("publish", True)),
            project_id=str(payload.get("project_id", "")).strip(),
        )
        if result.get("ok"):
            log_event("audiogen_generated", f"{result.get('emotion', '')}: {prompt[:80]}", "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/admin/audiogen/render-song":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        try:
            bars = int(payload.get("bars", 4) or 4)
            k = int(payload.get("k", 1) or 1)
        except (TypeError, ValueError):
            handler.send_json(400, {"error": "bars and k must be integers."})
            return True
        style_prefs = payload.get("style_prefs")
        if style_prefs is not None and not isinstance(style_prefs, dict):
            handler.send_json(400, {"error": "style_prefs must be an object."})
            return True
        result = audiogen_bridge.enqueue_full_song_render(
            emotion=str(payload.get("emotion", "")).strip(),
            bars=bars,
            k=k,
            publish=bool(payload.get("publish", True)),
            project_id=str(payload.get("project_id", "")).strip(),
            chain_to_automix=bool(payload.get("chain_to_automix", False)),
            genre=str(payload.get("genre", "")).strip(),
            style_prefs=style_prefs,
        )
        if result.get("ok"):
            job = result.get("job") or {}
            log_event("audiogen_full_song_queued", f"{job.get('emotion', '')}: {job.get('bars', '')} bars", "dashboard")
        handler.send_json(202 if result.get("ok") else 400, result)
        return True

    if path == "/api/admin/audiogen/render-job/cancel":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = audiogen_bridge.cancel_render_job(str(payload.get("id", "")).strip())
        handler.send_json(200 if result.get("ok") else 404, result)
        return True

    if path == "/api/admin/audiogen/render-job/retry":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = audiogen_bridge.retry_render_job(str(payload.get("id", "")).strip())
        handler.send_json(202 if result.get("ok") else 404, result)
        return True

    if path == "/api/admin/creative-lab/mix-review":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = creative_lab.review_generated_audio(payload)
        if result.get("ok"):
            review = result.get("review", {})
            log_event("creative_lab_mix_review_created", review.get("title", ""), "dashboard")
        handler.send_json(201 if result.get("ok") else 400, result)
        return True

    if path == "/api/admin/creative-lab/session":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = creative_lab.record_session_event(payload)
        if result.get("ok"):
            log_event("creative_lab_session_updated", result.get("session", {}).get("id", ""), "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/admin/creative-lab/feedback":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = creative_lab.record_feedback(payload)
        if result.get("ok"):
            log_event("creative_lab_feedback", result.get("feedback", {}).get("rating", ""), "dashboard")
        handler.send_json(201 if result.get("ok") else 400, result)
        return True

    if path == "/api/admin/creative-lab/repair":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = creative_lab.create_repair_artifacts(str(payload.get("feedback_id", "")))
        if result.get("ok"):
            log_event("creative_lab_repair_drafted", result.get("eval_case_id", ""), "dashboard")
        handler.send_json(201 if result.get("ok") and not result.get("already_exists") else 200 if result.get("ok") else 400, result)
        return True

    if path == "/api/admin/creative-lab/repair/promote":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = creative_lab.promote_repair(str(payload.get("feedback_id", "")))
        if result.get("ok"):
            log_event("creative_lab_repair_promoted", result.get("run", {}).get("eval_case_id", ""), "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/admin/creative-lab/repair/promote-eval":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = creative_lab.promote_repair_eval_case(str(payload.get("feedback_id", "")))
        if result.get("ok"):
            log_event("creative_lab_eval_promoted", result.get("case", {}).get("id", ""), "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/admin/creative-lab/repair/run-recommendation":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = creative_lab.run_repair_recommendation(str(payload.get("feedback_id", "")))
        if result.get("ok"):
            log_event("creative_lab_recommendation_run", result.get("workflow_kind", ""), "dashboard")
        handler.send_json(200 if result.get("ok") else 409 if result.get("manual_required") else 400, result)
        return True

    if path == "/api/admin/creative-lab/repair/export-training":
        result = creative_lab.export_repair_training_records()
        if result.get("ok"):
            log_event("creative_lab_repair_training_exported", str(result.get("count", 0)), "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/admin/creative-lab/repair/export-approved-training":
        result = creative_lab.export_approved_repair_training_records()
        if result.get("ok"):
            log_event("creative_lab_approved_repair_training_exported", str(result.get("count", 0)), "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/admin/creative-lab/repair/validate-approved-training":
        result = creative_lab.validate_approved_repair_training_export()
        if result.get("ok"):
            log_event("creative_lab_approved_repair_training_validated", "valid" if result.get("valid") else "invalid", "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/admin/creative-lab/repair/review-training-record":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = creative_lab.review_repair_training_record(
            str(payload.get("record_id", "")),
            str(payload.get("decision", "")),
            str(payload.get("note", "")),
        )
        if result.get("ok"):
            log_event("creative_lab_repair_training_reviewed", result.get("review", {}).get("decision", ""), "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    return False
