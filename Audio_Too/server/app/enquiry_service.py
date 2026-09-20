"""Transactional service for converting website enquiries into CRM records."""

from __future__ import annotations

from uuid import uuid4

import idempotency
from app.api_schemas import EnquiryConversionRequest
from db import connect, now


class EnquiryNotFound(LookupError):
    pass


def score_enquiry(service: str, message: str, deadline: str) -> int:
    score = 70
    if deadline.strip():
        score += 10
    if len(message.strip()) >= 120:
        score += 5
    if service.strip().lower() not in {"audio service", "other"}:
        score += 5
    return min(95, score)


def convert_enquiry(
    request: EnquiryConversionRequest,
    *,
    idempotency_key: str = "",
) -> tuple[int, dict]:
    """Convert one enquiry atomically and replay keyed retries safely."""
    operation = "business.enquiry.convert"
    request_hash = idempotency.payload_hash({"id": request.enquiry_id})

    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        replay = idempotency.replay(
            conn,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay:
            return replay

        row = conn.execute(
            "SELECT * FROM enquiries WHERE id = ?", (request.enquiry_id,)
        ).fetchone()
        if not row:
            raise EnquiryNotFound(f"Enquiry not found: {request.enquiry_id}")

        enquiry = dict(row)
        timestamp = now()
        if str(enquiry.get("status", "")).lower() == "converted":
            response = {
                "ok": True,
                "enquiry": enquiry,
                "client": None,
                "project": None,
                "lead": None,
                "already_converted": True,
            }
            idempotency.record(
                conn,
                operation=operation,
                key=idempotency_key,
                request_hash=request_hash,
                status_code=200,
                response=response,
                created_at=timestamp,
            )
            conn.commit()
            return 200, response

        name = str(enquiry.get("name", ""))
        email = str(enquiry.get("email", ""))
        service = str(enquiry.get("service", "Audio service"))
        message = str(enquiry.get("message", ""))
        deadline = str(enquiry.get("deadline", ""))
        score = score_enquiry(service, message, deadline)
        client_id = str(uuid4())[:8]
        project_id = str(uuid4())[:8]
        lead_id = str(uuid4())[:8]

        conn.execute(
            """INSERT INTO clients
               (id, name, contact, status, notes, created_at, updated_at, optimistic_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (client_id, name, email, "Active", message, timestamp, timestamp),
        )
        conn.execute(
            """INSERT INTO projects
               (id, client, project, service, status, deadline, waiting_on, follow_up,
                next_action, source, created_at, updated_at, optimistic_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                project_id,
                name,
                f"{service} enquiry",
                service,
                "New enquiry",
                deadline or "[Deadline]",
                "owner review",
                "",
                "Review enquiry and reply to client.",
                "website",
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            """INSERT INTO leads
               (id, lead, contact, type, service_fit, status, score, source, next_action,
                waiting_on, follow_up, created_at, updated_at, optimistic_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                lead_id,
                name,
                email,
                "website enquiry",
                service,
                "Warm",
                score,
                "website",
                "Reply to enquiry and qualify project.",
                "owner reply",
                "",
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            """UPDATE enquiries
               SET status = 'Converted', optimistic_version = ?, updated_at = ?
               WHERE id = ?""",
            (int(enquiry.get("optimistic_version") or 1) + 1, timestamp, request.enquiry_id),
        )

        response = {
            "ok": True,
            "enquiry": dict(
                conn.execute(
                    "SELECT * FROM enquiries WHERE id = ?", (request.enquiry_id,)
                ).fetchone()
            ),
            "client": dict(conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()),
            "project": dict(conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()),
            "lead": dict(conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()),
            "already_converted": False,
        }
        idempotency.record(
            conn,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            status_code=200,
            response=response,
            created_at=timestamp,
        )
        conn.commit()
        return 200, response
