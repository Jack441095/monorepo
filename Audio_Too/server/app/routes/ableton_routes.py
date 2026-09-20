"""Ableton dashboard GET/POST routes — Live/assistant-related data endpoints."""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import urlparse

import ableton_bridge
import demo_feedback
import llm_improvement
import lm_gaps
from app.routes.ableton_gap_routes import handle_ableton_gap_post
from app.api_errors import send_public_exception
from app.routes import thursday_routes

# Defined here (the sole consumer) rather than re-exported from thursday_routes:
# the 2026-07-20 thursday_routes rewrite dropped this constant, which broke
# server import at module load. Owning it locally removes that fragile coupling.
TRANSCRIPTION_SUFFIXES = {
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
}


def handle_ableton_post(
    handler,
    parsed_path: str,
    business_root: str,
    *,
    log_event: Callable[[str, str, str], None],
) -> bool:
    """Handle /api/ableton/* and other assistant POST routes.
    Returns True if handled, False to fall through."""
    parsed = urlparse("https://host" + parsed_path)
    path = parsed.path

    if handle_ableton_gap_post(handler, path, log_event=log_event):
        return True
    if thursday_routes.handle_thursday_post(handler, path):
        return True

    if path == "/api/ableton/note/polish":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        name = str(payload.get("name", "")).strip()
        if not name:
            handler.send_json(400, {"error": "name is required."})
            return True
        try:
            result = ableton_bridge.polish_note(name)
        except FileNotFoundError as exc:
            send_public_exception(handler, exc)
            return True
        if result.get("ok"):
            log_event("ableton_note_llm_polished", name, "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/ableton/note":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        name = str(payload.get("name", "")).strip()
        content = str(payload.get("content", ""))
        if not name:
            handler.send_json(400, {"error": "name is required."})
            return True
        try:
            note = ableton_bridge.write_note(name, content)
        except FileNotFoundError as exc:
            send_public_exception(handler, exc)
            return True
        log_event("ableton_note_saved", name, "dashboard")
        handler.send_json(200, {"ok": True, "note": note})
        return True

    if path == "/api/ableton/approve":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        name = str(payload.get("name", "")).strip()
        if not name:
            handler.send_json(400, {"error": "name is required."})
            return True
        try:
            note = ableton_bridge.approve_note(name)
        except FileNotFoundError as exc:
            send_public_exception(handler, exc)
            return True
        log_event("ableton_note_approved", name, "dashboard")
        gap_result = {}
        if str(payload.get("build", "")).lower() in {"yes", "true", "1"}:
            build = ableton_bridge.build_index()
            if build.get("ok"):
                gap_result = lm_gaps.on_note_approved(name)
                gap_result["index_built"] = True
        elif str(payload.get("retest_gaps", "")).lower() in {"yes", "true", "1"}:
            gap_result = lm_gaps.on_note_approved(name)
        handler.send_json(200, {"ok": True, "note": note, "gaps": gap_result})
        return True

    if path == "/api/ableton/fetch-web":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        url = str(payload.get("url", "")).strip()
        if not url:
            handler.send_json(400, {"error": "url is required."})
            return True
        try:
            result = ableton_bridge.fetch_web(url, payload)
        except ValueError as exc:
            send_public_exception(handler, exc)
            return True
        except OSError as exc:
            send_public_exception(handler, exc)
            return True
        if result.get("ok") and not result.get("skipped"):
            log_event("ableton_web_fetched", url, "dashboard")
        handler.send_json(200, result)
        return True

    if path == "/api/ableton/import-web-pack":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        limit = payload.get("limit")
        limit_value = int(limit) if str(limit or "").isdigit() else None
        force = str(payload.get("force", "")).lower() in {"yes", "true", "1"}
        suggested = str(payload.get("suggested", "")).lower() in {"yes", "true", "1"}
        result = ableton_bridge.import_web_pack(limit=limit_value, force=force, include_suggested=suggested)
        log_event("ableton_web_pack_imported", result.get("message", ""), "dashboard")
        handler.send_json(200, result)
        return True

    if path == "/api/ableton/train-chatbot":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = ableton_bridge.train_chatbot(
            approve=str(payload.get("approve", "")).lower() in {"yes", "true", "1"},
            build=str(payload.get("build", "")).lower() in {"yes", "true", "1"},
            force=str(payload.get("force", "")).lower() in {"yes", "true", "1"},
            use_llm=str(payload.get("llm", "")).lower() in {"yes", "true", "1"},
        )
        log_event("ableton_chatbot_trained", result.get("message", ""), "dashboard")
        handler.send_json(200, result)
        return True

    if path == "/api/ableton/paraphrase-all":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        fields = {
            key: str(payload[key])
            for key in ("creator", "tags", "type", "source", "force", "llm")
            if key in payload and payload[key] not in (None, "")
        }
        result = ableton_bridge.paraphrase_all(fields)
        log_event(
            "ableton_transcripts_paraphrased",
            f"{result.get('count', 0)} draft(s)",
            "dashboard",
        )
        handler.send_json(200, result)
        return True

    if path == "/api/ableton/build":
        result = ableton_bridge.build_index()
        if result.get("ok"):
            log_event("ableton_index_built", "chatbot index rebuilt", "dashboard")
            result["gaps_retest"] = lm_gaps.retest_all_open()
        handler.send_json(200, result)
        return True

    if path == "/api/ableton/improvement/run":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        kind = str(payload.get("kind", "")).strip().lower()
        result = llm_improvement.run_command(kind)
        if result.get("ok"):
            log_event("ableton_improvement_run", kind, "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/ableton/training-review":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = llm_improvement.save_training_review(payload)
        if result.get("ok"):
            log_event("kenn_training_review_saved", str(result.get("id", "")), "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/ableton/training-export":
        result = llm_improvement.export_reviewed_training()
        if result.get("ok"):
            log_event("kenn_reviewed_training_exported", str(result.get("path", "")), "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/ableton/hard-negatives-export":
        result = llm_improvement.export_hard_negatives()
        if result.get("ok"):
            log_event("kenn_hard_negatives_exported", str(result.get("path", "")), "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/ableton/route-memory-export":
        result = llm_improvement.export_route_memory()
        if result.get("ok"):
            log_event("kenn_route_memory_exported", str(result.get("path", "")), "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/ableton/suggested-notes/cluster":
        import suggested_notes_ops
        result = suggested_notes_ops.run_manual_clustering()
        if result.get("ok"):
            log_event("suggested_notes_clustered", f"Count: {result.get('count', 0)}", "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/ableton/suggested-notes/approve":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        draft_id = str(payload.get("id", "")).strip()
        if not draft_id:
            handler.send_json(400, {"error": "id is required."})
            return True
        import suggested_notes_ops
        result = suggested_notes_ops.approve_suggested_note(draft_id)
        if result.get("ok"):
            log_event("suggested_note_approved", result.get("note", ""), "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/ableton/suggested-notes/dismiss":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        draft_id = str(payload.get("id", "")).strip()
        if not draft_id:
            handler.send_json(400, {"error": "id is required."})
            return True
        import suggested_notes_ops
        result = suggested_notes_ops.dismiss_suggested_note(draft_id)
        if result.get("ok"):
            log_event("suggested_note_dismissed", draft_id, "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/ableton/suggested-notes/save":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        draft_id = str(payload.get("id", "")).strip()
        title = str(payload.get("title", "")).strip()
        content = str(payload.get("content", ""))
        if not draft_id or not title:
            handler.send_json(400, {"error": "id and title are required."})
            return True
        import suggested_notes_ops
        result = suggested_notes_ops.save_suggested_note_edits(draft_id, title, content)
        if result.get("ok"):
            log_event("suggested_note_saved", draft_id, "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/ableton/improvement/draft":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = llm_improvement.draft_agent_item(payload)
        if result.get("ok"):
            log_event("ableton_improvement_agent_drafted", result.get("note", ""), "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/ableton/improvement/retest-feedback":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        feedback_id = str(payload.get("id", "")).strip()
        if not feedback_id:
            handler.send_json(400, {"error": "id is required."})
            return True
        result = llm_improvement.retest_feedback_repair(feedback_id)
        if result.get("ok"):
            log_event("ableton_feedback_retested", f"{feedback_id}: {result.get('status', '')}", "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/ableton/improvement/draft-eval":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        feedback_id = str(payload.get("id", "")).strip()
        if not feedback_id:
            handler.send_json(400, {"error": "id is required."})
            return True
        result = llm_improvement.draft_eval_from_feedback(feedback_id)
        if result.get("ok"):
            log_event("ableton_feedback_eval_drafted", f"{feedback_id}: {result.get('path', '')}", "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/ableton/improvement/draft-query-eval":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        query_id = str(payload.get("id", "")).strip()
        if not query_id:
            handler.send_json(400, {"error": "id is required."})
            return True
        result = llm_improvement.draft_eval_from_query(query_id)
        if result.get("ok"):
            log_event("ableton_query_eval_drafted", f"{query_id}: {result.get('path', '')}", "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/ableton/improvement/mark-feedback-resolved":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        feedback_id = str(payload.get("id", "")).strip()
        if not feedback_id:
            handler.send_json(400, {"error": "id is required."})
            return True
        ok = demo_feedback.mark_repair_status(feedback_id, "resolved")
        if ok:
            log_event("ableton_feedback_marked_resolved", feedback_id, "dashboard")
        handler.send_json(200 if ok else 404, {"ok": ok, "feedback_id": feedback_id})
        return True

    if path == "/api/ableton/mix-version/save":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        session_id = str(payload.get("session_id", "")).strip()
        version_label = str(payload.get("version_label", "")).strip()
        metrics = payload.get("metrics", {})
        repair_chain = payload.get("repair_chain", {})
        if session_id and version_label:
            result = ableton_bridge.save_mix_version(session_id, version_label, metrics, repair_chain)
            handler.send_json(200, result)
        else:
            handler.send_json(400, {"ok": False, "error": "Missing session_id or version_label"})
        return True

    if path == "/api/ableton/feedback":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        rating = str(payload.get("rating", "")).strip().lower()
        if rating not in {"useful", "not_useful"}:
            handler.send_json(400, {"error": "rating must be useful or not_useful."})
            return True
        payload["channel"] = "dashboard"
        row = demo_feedback.record_feedback(payload)
        log_event("ableton_answer_feedback", f"{rating}: {row.get('question', '')[:80]}", "dashboard")
        handler.send_json(201, {"ok": True, "feedback": row})
        return True

    if path == "/api/ableton/live-suggestion":
        # Stage L near-term MVP: a Max for Live device sends a small slice of
        # live Live Object Model (LOM) state (track name, device chain, key
        # parameter values); this returns a grounded, weak_match-aware KENN
        # suggestion for the user to read and apply themselves. Read-only —
        # see kenn_handoff.explain_live_session_state's own docstring and
        # Stage L §L4/§L5 in docs/AUDIO_MVP_MASTER_PLAN.md for why nothing
        # here (or anywhere it calls into) writes back to the session.
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        track_name = str(payload.get("track_name", "")).strip()
        if not track_name:
            handler.send_json(400, {"error": "track_name is required."})
            return True
        device_chain = payload.get("device_chain")
        device_chain = [str(item) for item in device_chain] if isinstance(device_chain, list) else []
        key_params = payload.get("key_params")
        key_params = key_params if isinstance(key_params, dict) else {}
        genre = str(payload.get("genre", "")).strip() or None
        session_id = str(payload.get("session_id", "")).strip()
        from audio_analysis.integration.kenn_handoff import explain_live_session_state
        result = explain_live_session_state(
            track_name=track_name,
            device_chain=device_chain,
            key_params=key_params,
            genre=genre,
            session_id=session_id,
        )
        handler.send_json(200, result)
        return True

    if path == "/api/ableton/ask":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        question = str(payload.get("question", "")).strip()
        if not question:
            handler.send_json(400, {"error": "question is required."})
            return True
        try:
            limit = int(payload.get("limit", 5))
            history = payload.get("history") if isinstance(payload.get("history"), list) else []
            session_id = str(payload.get("session_id", "")).strip()
            project_id = str(payload.get("project_id", "")).strip()
            answer = ableton_bridge.ask(
                question,
                limit=limit,
                history=history,
                channel="dashboard",
                session_id=session_id,
                project_id=project_id,
            )
        except SystemExit as exc:
            send_public_exception(handler, exc)
            return True
        handler.send_json(200, answer)
        return True

    # Live OSC session/volume/pan control now lives in the KENN app itself
    # (studio/kenn/kenn/server.py) — see docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md.
    # The routes that used to live here were only ever called by the retired
    # ableton_visualizer.js.

    return False
