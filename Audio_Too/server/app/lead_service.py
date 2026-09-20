"""Transactional service for converting qualified leads into CRM work."""

from __future__ import annotations

from uuid import uuid4

import idempotency
from app.api_schemas import LeadConversionRequest
from db import connect, now


class LeadNotFound(LookupError):
    pass


class LeadNotConvertible(ValueError):
    pass


def convert_lead(
    request: LeadConversionRequest,
    *,
    idempotency_key: str = "",
) -> tuple[int, dict]:
    """Create client/project records and mark one lead converted atomically."""
    operation = "business.lead.convert"
    request_hash = idempotency.payload_hash({"id": request.lead_id})

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
            "SELECT * FROM leads WHERE id = ?", (request.lead_id,)
        ).fetchone()
        if not row:
            raise LeadNotFound(f"Lead not found: {request.lead_id}")
        lead = dict(row)
        current_status = str(lead.get("status") or "New").strip().lower()
        timestamp = now()

        if current_status == "converted":
            response = {
                "ok": True,
                "lead": lead,
                "client": None,
                "project": None,
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

        if current_status in {"closed", "not interested"}:
            raise LeadNotConvertible(
                f"Lead has status '{lead.get('status')}' and cannot be converted."
            )

        lead_name = str(lead.get("lead") or "Unknown")
        lead_contact = str(lead.get("contact") or "")
        lead_service = str(lead.get("service_fit") or "General")
        lead_source = str(lead.get("source") or "")
        client_id = str(uuid4())[:8]
        project_id = str(uuid4())[:8]
        converted_date = timestamp[:10]

        conn.execute(
            """INSERT INTO clients
               (id, name, contact, status, notes, created_at, updated_at, optimistic_version)
               VALUES (?, ?, ?, 'Active', ?, ?, ?, 1)""",
            (
                client_id,
                lead_name,
                lead_contact,
                f"Converted from lead (source: {lead_source}) on {converted_date}",
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            """INSERT INTO projects
               (id, client, project, service, status, deadline, waiting_on, follow_up,
                next_action, source, created_at, updated_at, optimistic_version)
               VALUES (?, ?, ?, ?, 'Open', ?, ?, '', ?, ?, ?, ?, 1)""",
            (
                project_id,
                lead_name,
                f"{lead_service} project",
                lead_service,
                str(lead.get("follow_up") or ""),
                "Initial brief / files from client",
                "Send welcome message and request project details",
                lead_source,
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            """UPDATE leads
               SET status = 'Converted', next_action = ?, waiting_on = ?,
                   optimistic_version = ?, updated_at = ?
               WHERE id = ?""",
            (
                f"Converted to client {client_id} and project {project_id}",
                "",
                int(lead.get("optimistic_version") or 1) + 1,
                timestamp,
                request.lead_id,
            ),
        )

        response = {
            "ok": True,
            "lead": dict(
                conn.execute(
                    "SELECT * FROM leads WHERE id = ?", (request.lead_id,)
                ).fetchone()
            ),
            "client": dict(
                conn.execute(
                    "SELECT * FROM clients WHERE id = ?", (client_id,)
                ).fetchone()
            ),
            "project": dict(
                conn.execute(
                    "SELECT * FROM projects WHERE id = ?", (project_id,)
                ).fetchone()
            ),
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
