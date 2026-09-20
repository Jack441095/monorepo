"""Business administration and log GET/POST routes."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

import ableton_bridge
import agent_bridge
from app.routes.admin_calendar_routes import handle_admin_calendar_post
import client_ops
import delivery_service
import draft_service
import enquiry_service
import idempotency
import lead_service
import portfolio_ops
import project_workspace
import path_safety
import status_transition_service
import stem_uploads
from app.api_schemas import (
    DraftCreateRequest,
    DraftDeliveryRequest,
    DraftSendRequest,
    EnquiryConversionRequest,
    LeadConversionRequest,
    SchemaValidationError,
)
from db import TABLES, list_records, summary as db_summary
from invoice_tokens import invoice_urls
from Shared.activity_log import list_events
from Shared.backup import backup_status, run_backup
from Shared.due_work import collect_due_items
from upload_tokens import upload_url


def admin_hub() -> dict:
    """Load rich business dashboard state."""
    host = os.getenv("AUDIO_TOO_HOST", "127.0.0.1")
    port = int(os.getenv("AUDIO_TOO_PORT", "8080"))

    transcript_items = ableton_bridge.list_transcript_items()
    transcript_drafts = sum(
        1 for item in transcript_items if str(item.get("status", "")).lower() in {"draft", "unmarked"}
    )
    drafts = [item for item in list_records("drafts") if item.get("status", "Pending") == "Pending"]
    projects = [
        item for item in list_records("projects") if item.get("status", "Open") not in {"Closed", "Complete", "Completed"}
    ]
    due_all = collect_due_items(list_records, overdue_only=False)
    due_overdue = [item for item in due_all if item.get("overdue")]
    recent_enquiries = list_records("enquiries")[:6]
    return {
        "summary": db_summary(),
        "activity": list_events(12),
        "ableton": {
            "transcript_total": len(transcript_items),
            "transcript_drafts": transcript_drafts,
            "web": ableton_bridge.web_health(),
        },
        "pending_drafts": drafts[:6],
        "recent_projects": projects[:6],
        "due_items": due_all[:12],
        "overdue_count": len(due_overdue),
        "due_count": len(due_all),
        "recent_enquiries": recent_enquiries,
        "client_ops": client_ops.snapshot(),
        "backup": backup_status(),
        "public_site": f"http://{host}:{port}/",
        "ableton_web_url": ableton_bridge.web_chat_url(),
    }


def handle_admin_get(handler, parsed_path: str) -> bool:
    """Handle /api/admin/* and other business admin GET routes.
    Returns True if handled, False to fall through."""
    parsed = urlparse("https://host" + parsed_path)
    path = parsed.path

    if path == "/api/summary":
        handler.send_json(200, db_summary())
        return True

    if path == "/api/records":
        handler.send_json(200, {name: list_records(name) for name in TABLES.keys()})
        return True

    if path == "/api/invoices":
        handler.send_json(200, {"invoices": list_records("invoices")})
        return True

    if path == "/api/admin/dashboard":
        handler.send_json(
            200,
            {
                "summary": db_summary(),
                "records": {name: list_records(name) for name in TABLES.keys()},
                "drafts": list_records("drafts"),
            },
        )
        return True

    if path == "/api/admin/hub":
        handler.send_json(200, admin_hub())
        return True

    if path == "/api/admin/calendar":
        from thursday.scheduling import _load_reminders
        handler.send_json(200, {"events": _load_reminders()})
        return True

    if path == "/api/admin/stem-uploads":
        project_id = parse_qs(parsed.query).get("project_id", [""])[0]
        handler.send_json(200, {"items": stem_uploads.list_uploads(project_id=project_id)})
        return True

    if path == "/api/admin/client-ops":
        handler.send_json(200, client_ops.snapshot())
        return True

    if path == "/api/admin/portfolio-ops":
        handler.send_json(200, portfolio_ops.snapshot())
        return True

    if path == "/api/admin/projects/workspace":
        project_id = parse_qs(parsed.query).get("id", [""])[0]
        result = project_workspace.workspace(project_id)
        handler.send_json(200 if result.get("ok") else 404, result)
        return True

    if path == "/api/admin/draft-deliveries/status":
        delivery_id = parse_qs(parsed.query).get("id", [""])[0]
        try:
            delivery_id = path_safety.validate_identifier(
                delivery_id, label="delivery ID"
            )
        except ValueError as exc:
            handler.send_json(400, {"error": str(exc)})
            return True
        delivery = delivery_service.get_delivery(delivery_id)
        if not delivery:
            handler.send_json(404, {"error": "Delivery not found."})
            return True
        handler.send_json(200, {"ok": True, "delivery": delivery})
        return True

    if path.startswith("/api/admin/"):
        table = path.rsplit("/", 1)[-1]
        if table in TABLES:
            handler.send_json(200, {table: list_records(table)})
            return True

    return False


def handle_admin_post(handler, parsed_path: str, *, log_event: Callable[[str, str, str], None]) -> bool:
    """Handle /api/admin/* business admin POST routes.
    Returns True if handled, False to fall through."""
    parsed = urlparse("https://host" + parsed_path)
    path = parsed.path
    host = os.getenv("AUDIO_TOO_HOST", "127.0.0.1")
    port = int(os.getenv("AUDIO_TOO_PORT", "8080"))

    if handle_admin_calendar_post(handler, path, log_event=log_event):
        return True

    if path == "/api/admin/enquiries/convert":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        try:
            request = EnquiryConversionRequest.from_payload(payload)
        except SchemaValidationError as exc:
            handler.send_json(
                400,
                {"error": exc.message, "code": "validation_error", "details": exc.details},
            )
            return True
        try:
            key = idempotency.header_value(handler.headers)
            status, result = enquiry_service.convert_enquiry(
                request, idempotency_key=key
            )
        except idempotency.IdempotencyConflict as exc:
            handler.send_json(
                409,
                {"error": str(exc), "code": "idempotency_conflict", "details": {}},
            )
            return True
        except enquiry_service.EnquiryNotFound:
            handler.send_json(
                404,
                {"error": "Enquiry not found.", "code": "enquiry_not_found", "details": {}},
            )
            return True
        except ValueError as exc:
            handler.send_json(
                400,
                {"error": str(exc), "code": "invalid_idempotency_key", "details": {}},
            )
            return True
        if not result.get("already_converted"):
            log_event(
                "enquiry_converted",
                f"{request.enquiry_id} → client {result['client'].get('id', '')}",
                "dashboard",
            )
        handler.send_json(status, result)
        return True

    if path == "/api/admin/leads/convert":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        try:
            request = LeadConversionRequest.from_payload(payload)
        except SchemaValidationError as exc:
            handler.send_json(
                400,
                {"error": exc.message, "code": "validation_error", "details": exc.details},
            )
            return True
        try:
            key = idempotency.header_value(handler.headers)
            status, result = lead_service.convert_lead(
                request, idempotency_key=key
            )
        except idempotency.IdempotencyConflict as exc:
            handler.send_json(
                409,
                {"error": str(exc), "code": "idempotency_conflict", "details": {}},
            )
            return True
        except lead_service.LeadNotFound:
            handler.send_json(
                404,
                {"error": "Lead not found.", "code": "lead_not_found", "details": {}},
            )
            return True
        except lead_service.LeadNotConvertible as exc:
            handler.send_json(
                409,
                {"error": str(exc), "code": "lead_not_convertible", "details": {}},
            )
            return True
        except ValueError as exc:
            handler.send_json(
                400,
                {"error": str(exc), "code": "invalid_idempotency_key", "details": {}},
            )
            return True
        if not result.get("already_converted"):
            log_event(
                "lead_converted",
                f"{request.lead_id} → client {result['client'].get('id', '')}",
                "dashboard",
            )
        handler.send_json(status, result)
        return True

    if path == "/api/admin/enquiries/draft-reply":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        enquiry_id = str(payload.get("id", "")).strip()
        if not enquiry_id:
            handler.send_json(400, {"error": "id is required."})
            return True
        result = client_ops.draft_enquiry_reply(enquiry_id)
        if result.get("ok"):
            log_event("client_intake_reply_drafted", enquiry_id, "dashboard")
        handler.send_json(200 if result.get("ok") else 404, result)
        return True

    if path == "/api/admin/drafts/send":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        try:
            request = DraftSendRequest.from_payload(payload)
        except SchemaValidationError as exc:
            handler.send_json(
                400,
                {"error": exc.message, "code": "validation_error", "details": exc.details},
            )
            return True
        try:
            key = idempotency.header_value(handler.headers)
            status, result = draft_service.send_draft(request, idempotency_key=key)
        except idempotency.IdempotencyConflict as exc:
            handler.send_json(
                409,
                {"error": str(exc), "code": "idempotency_conflict", "details": {}},
            )
            return True
        except draft_service.DraftNotFound:
            handler.send_json(
                404,
                {"error": "Draft not found.", "code": "draft_not_found", "details": {}},
            )
            return True
        except draft_service.DraftNotSendable as exc:
            handler.send_json(
                409,
                {"error": str(exc), "code": "draft_not_sendable", "details": {}},
            )
            return True
        except ValueError as exc:
            handler.send_json(
                400,
                {"error": str(exc), "code": "invalid_idempotency_key", "details": {}},
            )
            return True
        if not result.get("already_sent"):
            log_event("draft_sent", request.draft_id, "dashboard")
        handler.send_json(status, result)
        return True

    if path == "/api/admin/draft-deliveries":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        try:
            request = DraftDeliveryRequest.from_payload(payload)
        except SchemaValidationError as exc:
            handler.send_json(
                400,
                {"error": exc.message, "code": "validation_error", "details": exc.details},
            )
            return True
        try:
            key = idempotency.header_value(handler.headers)
            status, result = delivery_service.queue_draft_delivery(
                request, idempotency_key=key
            )
        except idempotency.IdempotencyConflict as exc:
            handler.send_json(
                409,
                {"error": str(exc), "code": "idempotency_conflict", "details": {}},
            )
            return True
        except delivery_service.DraftNotFound:
            handler.send_json(
                404,
                {"error": "Draft not found.", "code": "draft_not_found", "details": {}},
            )
            return True
        except delivery_service.DraftNotApproved as exc:
            handler.send_json(
                409,
                {"error": str(exc), "code": "draft_not_approved", "details": {}},
            )
            return True
        except delivery_service.DeliveryConflict as exc:
            handler.send_json(
                409,
                {"error": str(exc), "code": "delivery_conflict", "details": {}},
            )
            return True
        except ValueError as exc:
            handler.send_json(
                400,
                {"error": str(exc), "code": "invalid_idempotency_key", "details": {}},
            )
            return True
        if not result.get("already_queued"):
            log_event(
                "draft_delivery_queued",
                f"{request.draft_id} → {result['delivery']['id']}",
                "dashboard",
            )
        handler.send_json(status, result)
        return True

    if path == "/api/admin/portfolio/publish-project":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = portfolio_ops.publish_project(str(payload.get("id", "")).strip())
        if result.get("ok"):
            log_event("portfolio_project_published", result.get("entry", {}).get("title", ""), "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/admin/portfolio/publish-audio":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = portfolio_ops.publish_audio(
            str(payload.get("filename", "")).strip(),
            title=str(payload.get("title", "")).strip(),
            description=str(payload.get("description", "")).strip(),
        )
        if result.get("ok"):
            log_event("portfolio_audio_published", result.get("entry", {}).get("title", ""), "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/admin/agent":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        task = str(payload.get("task", "")).strip()
        agent = str(payload.get("agent", "auto")).strip() or "auto"
        if not task:
            handler.send_json(400, {"error": "task is required."})
            return True
        result = agent_bridge.run_agent_task(task, agent=agent)
        status = 200 if result.get("ok") else (403 if "not allowed" in str(result.get("error", "")).lower() else 500)
        handler.send_json(status, result)
        return True

    if path == "/api/admin/status":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        try:
            request = status_transition_service.StatusTransitionRequest.from_payload(payload)
            record = status_transition_service.transition_status(request)
        except status_transition_service.StatusTransitionError as exc:
            handler.send_json(exc.status_code, {"error": exc.message})
            return True
        log_event(
            "record_status_updated",
            f"{request.table} {request.record_id} → {request.status}",
            "dashboard",
        )
        handler.send_json(200, {"ok": True, "record": record})
        return True

    if path == "/api/admin/draft":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        try:
            request = DraftCreateRequest.from_payload(payload)
        except SchemaValidationError as exc:
            handler.send_json(
                400,
                {"error": exc.message, "code": "validation_error", "details": exc.details},
            )
            return True
        try:
            key = idempotency.header_value(handler.headers)
            status, result = draft_service.create_draft(request, idempotency_key=key)
        except idempotency.IdempotencyConflict as exc:
            handler.send_json(409, {"error": str(exc), "code": "idempotency_conflict", "details": {}})
            return True
        except ValueError as exc:
            handler.send_json(
                400, {"error": str(exc), "code": "invalid_idempotency_key", "details": {}}
            )
            return True
        draft = result.get("draft", {})
        log_event("draft_created", f"{draft.get('recipient', '')} – {draft.get('subject', '')}", "dashboard")
        handler.send_json(status, result)
        return True

    if path == "/api/admin/projects/stem-link":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        project_id = str(payload.get("project_id", "")).strip()
        if not project_id:
            handler.send_json(400, {"error": "project_id is required."})
            return True
        if not stem_uploads.find_project(project_id):
            handler.send_json(404, {"error": "Project not found."})
            return True
        ttl_days = int(payload.get("ttl_days", 14) or 14)
        ttl_days = max(1, min(60, ttl_days))
        link = upload_url(project_id, host=host, port=port, ttl_seconds=ttl_days * 86400)
        log_event("stem_upload_link_created", project_id, "dashboard")
        handler.send_json(200, {"ok": True, **link})
        return True

    if path == "/api/admin/invoice-links":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        ids = payload.get("ids") or []
        if not isinstance(ids, list):
            handler.send_json(400, {"error": "ids must be a list."})
            return True
        links = {
            str(invoice_id): invoice_urls(str(invoice_id), host=host, port=port)
            for invoice_id in ids
            if str(invoice_id).strip()
        }
        handler.send_json(200, {"ok": True, "links": links})
        return True

    if path == "/api/admin/backup":
        path_res = run_backup()
        log_event("backup_created", str(path_res), "dashboard")
        handler.send_json(200, {"ok": True, "path": str(path_res), "message": f"Backup created: {path_res}"})
        return True

    return False
