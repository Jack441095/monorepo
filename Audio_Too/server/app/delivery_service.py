"""Transactional queue service for reviewed external draft deliveries."""

from __future__ import annotations

import json
from uuid import uuid4

import idempotency
from app.api_schemas import DraftDeliveryRequest
from db import connect, now


class DraftNotFound(LookupError):
    pass


class DraftNotApproved(ValueError):
    pass


class DeliveryConflict(ValueError):
    pass


def public_delivery(row: dict) -> dict:
    """Return delivery state without exposing message bodies or worker internals."""
    return {
        key: row.get(key)
        for key in (
            "id",
            "kind",
            "aggregate_type",
            "aggregate_id",
            "recipient",
            "subject",
            "status",
            "attempts",
            "sent_at",
            "provider_receipt",
            "followup_id",
            "last_error",
            "created_at",
            "updated_at",
        )
    }


def queue_draft_delivery(
    request: DraftDeliveryRequest,
    *,
    idempotency_key: str = "",
) -> tuple[int, dict]:
    operation = "business.draft.delivery.create"
    request_payload = {
        "id": request.draft_id,
        "recipient_email": request.recipient_email,
    }
    request_hash = idempotency.payload_hash(request_payload)

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

        draft_row = conn.execute(
            "SELECT * FROM drafts WHERE id = ?", (request.draft_id,)
        ).fetchone()
        if not draft_row:
            raise DraftNotFound(f"Draft not found: {request.draft_id}")
        draft = dict(draft_row)

        existing_row = conn.execute(
            """SELECT * FROM delivery_outbox
               WHERE kind = 'email' AND aggregate_type = 'draft' AND aggregate_id = ?""",
            (request.draft_id,),
        ).fetchone()
        if existing_row:
            existing = dict(existing_row)
            if str(existing.get("recipient")) != request.recipient_email:
                raise DeliveryConflict(
                    "This draft already has a delivery for a different recipient."
                )
            response = {
                "ok": True,
                "delivery": public_delivery(existing),
                "already_queued": True,
            }
            idempotency.record(
                conn,
                operation=operation,
                key=idempotency_key,
                request_hash=request_hash,
                status_code=200,
                response=response,
                created_at=now(),
            )
            conn.commit()
            return 200, response

        if str(draft.get("status") or "").lower() != "approved":
            raise DraftNotApproved("Only an approved draft can be queued for delivery.")

        delivery_id = str(uuid4())[:8]
        timestamp = now()
        subject = str(draft.get("subject") or "Audio_Too message").strip()
        body = str(draft.get("body") or "")
        payload = {"text_body": body}
        conn.execute(
            """INSERT INTO delivery_outbox
               (id, kind, aggregate_type, aggregate_id, recipient, subject,
                payload_json, status, attempts, created_at, updated_at)
               VALUES (?, 'email', 'draft', ?, ?, ?, ?, 'queued', 0, ?, ?)""",
            (
                delivery_id,
                request.draft_id,
                request.recipient_email,
                subject,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            """UPDATE drafts
               SET status = 'Delivery queued', optimistic_version = ?, updated_at = ?
               WHERE id = ?""",
            (int(draft.get("optimistic_version") or 1) + 1, timestamp, request.draft_id),
        )
        delivery = dict(
            conn.execute(
                "SELECT * FROM delivery_outbox WHERE id = ?", (delivery_id,)
            ).fetchone()
        )
        response = {
            "ok": True,
            "delivery": public_delivery(delivery),
            "already_queued": False,
        }
        idempotency.record(
            conn,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            status_code=202,
            response=response,
            created_at=timestamp,
        )
        conn.commit()
        return 202, response


def get_delivery(delivery_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM delivery_outbox WHERE id = ?", (delivery_id,)
        ).fetchone()
    return public_delivery(dict(row)) if row else None


def queue_enquiry_notification(
    *,
    enquiry_id: str,
    destination: str,
    name: str,
    email: str,
    service: str,
    message: str,
    deadline: str = "",
) -> dict:
    """Durably queue the configured owner notification for one new enquiry."""
    subject = f"Audio_Too enquiry — {name} ({service})"
    body = "\n".join(
        [
            "New project enquiry from the Audio_Too website.",
            "",
            f"Name: {name}",
            f"Email: {email}",
            f"Service: {service}",
            f"Deadline: {deadline or '(not specified)'}",
            f"Enquiry record: {enquiry_id}",
            "",
            "Message:",
            message,
            "",
            "Open the dashboard: http://127.0.0.1:8080/dashboard",
        ]
    )
    timestamp = now()
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            """SELECT * FROM delivery_outbox
               WHERE kind = 'email' AND aggregate_type = 'enquiry' AND aggregate_id = ?""",
            (enquiry_id,),
        ).fetchone()
        if existing:
            conn.commit()
            return public_delivery(dict(existing))
        delivery_id = str(uuid4())[:8]
        conn.execute(
            """INSERT INTO delivery_outbox
               (id, kind, aggregate_type, aggregate_id, recipient, subject,
                payload_json, status, attempts, created_at, updated_at)
               VALUES (?, 'email', 'enquiry', ?, ?, ?, ?, 'queued', 0, ?, ?)""",
            (
                delivery_id,
                enquiry_id,
                destination,
                subject,
                json.dumps(
                    {"text_body": body}, sort_keys=True, separators=(",", ":")
                ),
                timestamp,
                timestamp,
            ),
        )
        row = conn.execute(
            "SELECT * FROM delivery_outbox WHERE id = ?", (delivery_id,)
        ).fetchone()
        conn.commit()
    return public_delivery(dict(row))


def queue_automix_notification(
    *,
    job_id: str,
    project_id: str,
    destination: str,
    version: int,
    download_url: str,
) -> dict:
    """Queue one mix-ready notification behind the external-action worker."""
    timestamp = now()
    subject = f"Your automated mixdown is ready (v{version})"
    body = "\n".join(
        [
            "Hello,",
            "",
            f"Your assisted mixdown for project '{project_id}' (version {version}) is ready.",
            "Download the package, report, and decision log here:",
            download_url,
            "",
            "Please review the result before client delivery.",
        ]
    )
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            """SELECT * FROM delivery_outbox
               WHERE kind = 'email' AND aggregate_type = 'automix_job' AND aggregate_id = ?""",
            (job_id,),
        ).fetchone()
        if existing:
            conn.commit()
            return public_delivery(dict(existing))
        delivery_id = str(uuid4())[:8]
        conn.execute(
            """INSERT INTO delivery_outbox
               (id, kind, aggregate_type, aggregate_id, recipient, subject,
                payload_json, status, attempts, created_at, updated_at)
               VALUES (?, 'email', 'automix_job', ?, ?, ?, ?, 'queued', 0, ?, ?)""",
            (
                delivery_id,
                job_id,
                destination,
                subject,
                json.dumps(
                    {"text_body": body}, sort_keys=True, separators=(",", ":")
                ),
                timestamp,
                timestamp,
            ),
        )
        row = conn.execute(
            "SELECT * FROM delivery_outbox WHERE id = ?", (delivery_id,)
        ).fetchone()
        conn.commit()
    return public_delivery(dict(row))
