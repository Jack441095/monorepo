"""Public and authentication POST routes for the website server."""

from __future__ import annotations

import json
from collections.abc import Callable

import automix_public
import automix_public_tokens
import business_chat
import enquiry_guard
import enquiries as enquiry_store
import mix_report_tokens
import notify
import podcast_report_store
import podcast_report_tokens
import stem_separation_bridge
import stem_separation_tokens
import stem_uploads
import studio_tips
from audio_analysis.mix_review import mix_review


LogEvent = Callable[[str, str, str], None]


def handle_enquiry(payload: dict) -> dict:
    clean = enquiry_guard.validate_enquiry_payload(payload)
    enquiry = enquiry_store.create_enquiry(clean)
    return {"enquiry": enquiry}


def handle_post(handler, path: str, *, log_event: LogEvent) -> bool:

    if path == "/api/public/stem-upload":
        if enquiry_guard.is_rate_limited(handler.client_address, scope="public_stem_upload"):
            handler.send_json(429, {"error": "Too many uploads. Try again later."})
            return True
        content_type = handler.headers.get("Content-Type", "")
        try:
            body = handler.read_body_bytes()
            result = stem_uploads.handle_multipart_upload(content_type, body)
        except ValueError as exc:
            handler.send_json(400, {"error": str(exc)})
            return True
        if result.get("ok"):
            log_event(
                "stem_upload_received",
                f"{result.get('project_id', '')} · {result.get('filename', '')}",
                "client",
            )
            handler.send_json(201, result)
        else:
            handler.send_json(400, result)
        return True

    if path == "/api/public/podcast-check":
        if enquiry_guard.is_rate_limited(handler.client_address, scope="public_podcast_check"):
            handler.send_json(429, {"error": "Too many checks. Try again later."})
            return True
        try:
            content_type = handler.headers.get("Content-Type", "")
            result = mix_review.handle_multipart_podcast_check(content_type, handler.read_body_bytes())
        except Exception as exc:
            handler.send_json(500, {"error": f"Podcast check failed: {exc}"})
            return True
        if result.get("ok"):
            report = result.get("report", {})
            report_id = podcast_report_store.save_podcast_report(
                title=str(result.get("title", "")),
                target=str(report.get("target", "")),
                report=report,
                html_report=str(result.get("html_report", "")),
            )
            token = podcast_report_tokens.make_podcast_report_token(report_id)
            result["id"] = report_id
            result["token"] = token
            result["report_path"] = f"/podcast-report/{report_id}?token={token}"
            log_event(
                "public_podcast_check",
                f"{report.get('target_label', '')} · score {report.get('score', '')}",
                "website",
            )
            handler.send_json(200, result)
        else:
            handler.send_json(400, result)
        return True

    if path == "/api/public/mix-doctor":
        if enquiry_guard.is_rate_limited(handler.client_address, scope="public_mix_doctor"):
            handler.send_json(429, {"error": "Too many uploads. Try again later."})
            return True
        try:
            content_type = handler.headers.get("Content-Type", "")
            result = mix_review.handle_multipart_review(content_type, handler.read_body_bytes())
        except Exception as exc:
            handler.send_json(500, {"error": f"Mix Doctor upload failed: {exc}"})
            return True
        if result.get("ok"):
            review_id = str(result.get("id", ""))
            token = mix_report_tokens.make_report_token(review_id)
            result["token"] = token
            result["report_path"] = f"/mix-report/{review_id}?token={token}"
            result["status_path"] = f"/mix-report/{review_id}/status?token={token}"
            log_event("public_mix_doctor_upload", review_id, "website")
            handler.send_json(201, result)
        else:
            handler.send_json(400, result)
        return True

    if path == "/api/public/delivery-check":
        if enquiry_guard.is_rate_limited(handler.client_address, scope="public_delivery_check"):
            handler.send_json(429, {"error": "Too many checks. Try again later."})
            return True
        try:
            content_type = handler.headers.get("Content-Type", "")
            result = mix_review.handle_multipart_delivery_conform(content_type, handler.read_body_bytes())
        except Exception as exc:
            handler.send_json(500, {"error": f"Delivery check failed: {exc}"})
            return True
        if result.get("ok"):
            report = result.get("report", {})
            log_event(
                "public_delivery_check",
                f"{report.get('target_label', '')} · score {report.get('score', '')}",
                "website",
            )
            handler.send_json(200, result)
        else:
            handler.send_json(400, result)
        return True

    if path == "/api/public/automix-start":
        if enquiry_guard.is_rate_limited(handler.client_address, scope="public_automix_start"):
            handler.send_json(429, {"error": "Too many uploads. Try again later."})
            return True
        try:
            content_type = handler.headers.get("Content-Type", "")
            fields = stem_uploads.parse_multipart_form(content_type, handler.read_body_bytes())
        except ValueError as exc:
            handler.send_json(400, {"error": str(exc)})
            return True
        # Multiple stems share the multipart body under distinct field
        # names (stem_0, stem_1, ...) -- parse_multipart_form overwrites
        # same-named fields, so a single "file" field (like every other
        # single-upload endpoint here uses) can't carry more than one.
        files: list[tuple[bytes, str]] = []
        index = 0
        while f"stem_{index}" in fields:
            file_bytes = fields.get(f"stem_{index}")
            if isinstance(file_bytes, (bytes, bytearray)):
                filename = str(fields.get(f"stem_{index}__filename", f"stem_{index}.wav"))
                files.append((bytes(file_bytes), filename))
            index += 1
        if not files:
            handler.send_json(400, {"error": "No stem files provided (expected stem_0, stem_1, ...)."})
            return True
        genre = str(fields.get("genre", "pop") or "pop")
        result = automix_public.start_public_automix(files, genre=genre)
        if not result.get("ok"):
            handler.send_json(400, result)
            return True
        job_id = result["job_id"]
        token = automix_public_tokens.make_job_token(job_id)
        log_event("public_automix_start_upload", f"{result['project_id']} · {len(files)} file(s)", "website")
        handler.send_json(202, {
            "ok": True,
            "project_id": result["project_id"],
            "job_id": job_id,
            "status": result["status"],
            "token": token,
            "status_path": f"/api/public/automix-start/status?id={job_id}&token={token}",
        })
        return True

    if path == "/api/public/stem-separate":
        if enquiry_guard.is_rate_limited(handler.client_address, scope="public_stem_separate"):
            handler.send_json(429, {"error": "Too many uploads. Try again later."})
            return True
        try:
            content_type = handler.headers.get("Content-Type", "")
            fields = stem_uploads.parse_multipart_form(content_type, handler.read_body_bytes())
        except ValueError as exc:
            handler.send_json(400, {"error": str(exc)})
            return True
        file_bytes = fields.get("file")
        if not isinstance(file_bytes, (bytes, bytearray)):
            handler.send_json(400, {"error": "Missing file field."})
            return True
        filename = str(fields.get("file__filename", "mix.wav"))
        result = stem_separation_bridge.enqueue_separation(bytes(file_bytes), filename)
        if not result.get("ok"):
            handler.send_json(400, result)
            return True
        job = result["job"]
        token = stem_separation_tokens.make_job_token(job["id"])
        log_event("public_stem_separate_upload", job["id"], "website")
        handler.send_json(202, {
            "ok": True,
            "id": job["id"],
            "status": job["status"],
            "token": token,
            "status_path": f"/api/public/stem-separate/status?id={job['id']}&token={token}",
        })
        return True

    if path == "/api/public/tips/ask":
        if enquiry_guard.is_rate_limited(handler.client_address, scope="public_tips"):
            handler.send_json(429, {"error": "Too many questions. Try again later."})
            return True
        try:
            payload = handler.read_json_body()
            question = studio_tips.validate_question(payload)
            session_id = str(payload.get("session_id", "")).strip()
            result = studio_tips.ask_public(question, session_id=session_id)
        except ValueError as exc:
            handler.send_json(400, {"error": str(exc)})
            return True
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        except SystemExit as exc:
            handler.send_json(500, {"error": str(exc)})
            return True
        log_event("public_studio_tips_ask", question[:120], "website")
        handler.send_json(200, result)
        return True

    if path == "/api/public/ask":
        if enquiry_guard.is_rate_limited(handler.client_address, scope="public_ask"):
            handler.send_json(
                429,
                {"error": "Too many questions. Try again later or use the enquiry form."},
            )
            return True
        try:
            payload = handler.read_json_body()
            question = business_chat.validate_question(payload)
            result = business_chat.answer_question(question)
        except ValueError as exc:
            handler.send_json(400, {"error": str(exc)})
            return True
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        except FileNotFoundError as exc:
            handler.send_json(500, {"error": str(exc)})
            return True
        log_event("public_business_ask", question[:120], "website")
        handler.send_json(200, result)
        return True

    if path == "/api/enquiry":
        if enquiry_guard.is_rate_limited(handler.client_address):
            handler.send_json(429, {"error": "Too many enquiries. Try again later."})
            return True
        try:
            payload = handler.read_json_body()
            result = handle_enquiry(payload)
        except enquiry_guard.HoneypotError:
            handler.send_json(201, {"ok": True})
            return True
        except ValueError as exc:
            handler.send_json(400, {"error": str(exc)})
            return True
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        enquiry = result["enquiry"]
        detail = f"{enquiry.get('name', '')} – {enquiry.get('service', '')} ({enquiry.get('id', '')})"
        log_event("website_enquiry_received", detail, "website")
        notify.notify_new_enquiry(
            str(enquiry.get("name", "Someone")),
            str(enquiry.get("service", "Audio service")),
            email=str(enquiry.get("email", "")),
            message=str(enquiry.get("message", "")),
            deadline=str(enquiry.get("deadline", "")),
            client_id=str(enquiry.get("id", "")),
        )
        handler.send_json(201, {"ok": True, "enquiry": enquiry})
        return True

    return False
