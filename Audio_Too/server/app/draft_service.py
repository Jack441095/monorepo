"""Transactional business service for sending approved drafts."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import event_store
import idempotency
from app.api_schemas import DraftCreateRequest, DraftSendRequest
from db import connect, now


class DraftNotFound(LookupError):
    pass


class DraftNotSendable(ValueError):
    pass


def create_draft(
    request: DraftCreateRequest,
    *,
    idempotency_key: str = "",
) -> tuple[int, dict]:
    """Create a draft and emit `draft.created` in one transaction (with replay)."""
    operation = "business.draft.create"
    request_hash = idempotency.payload_hash({
        "type": request.type,
        "recipient": request.recipient,
        "subject": request.subject,
        "body": request.body,
        "source": request.source,
    })

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

        draft_id = str(uuid4())[:8]
        timestamp = now()
        conn.execute(
            """INSERT INTO drafts
               (id, type, recipient, subject, body, status, source,
                created_at, updated_at, optimistic_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                draft_id,
                request.type,
                request.recipient,
                request.subject,
                request.body,
                "Pending",
                request.source,
                timestamp,
                timestamp,
                1,
            ),
        )
        draft = dict(conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone())
        event_store.append_in_transaction(
            conn,
            event_type="draft.created",
            aggregate_type="drafts",
            aggregate_id=draft_id,
            actor_id="dashboard",
            payload={
                "type": request.type,
                "recipient": request.recipient,
                "subject": request.subject[:120],
                "source": request.source,
            },
        )
        response = {"ok": True, "draft": draft}
        idempotency.record(
            conn,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            status_code=201,
            response=response,
            created_at=timestamp,
        )
        conn.commit()
        return 201, response


def send_draft(
    request: DraftSendRequest,
    *,
    idempotency_key: str = "",
) -> tuple[int, dict]:
    """Mark a draft sent and create exactly one follow-up in one transaction."""
    operation = "business.draft.send"
    request_hash = idempotency.payload_hash({"id": request.draft_id})

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
            "SELECT * FROM drafts WHERE id = ?", (request.draft_id,)
        ).fetchone()
        if not row:
            raise DraftNotFound(f"Draft not found: {request.draft_id}")

        draft = dict(row)
        current_status = str(draft.get("status") or "").lower()
        timestamp = now()
        if current_status == "sent":
            response = {
                "ok": True,
                "draft": draft,
                "followup": None,
                "already_sent": True,
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

        if current_status not in {"pending", "approved"}:
            raise DraftNotSendable(
                f"Draft has status '{draft.get('status')}' and cannot be sent."
            )

        new_version = int(draft.get("optimistic_version") or 1) + 1
        conn.execute(
            """UPDATE drafts
               SET status = 'Sent', optimistic_version = ?, updated_at = ?
               WHERE id = ?""",
            (new_version, timestamp, request.draft_id),
        )

        followup_id = str(uuid4())[:8]
        followup_due = (date.today() + timedelta(days=7)).isoformat()
        draft_type = str(draft.get("type") or "message")
        recipient = str(draft.get("recipient") or "Unknown")
        subject = str(draft.get("subject") or "")
        conn.execute(
            """INSERT INTO followups
               (id, owner, subject, source, status, due, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                followup_id,
                "draft-sender",
                f"Follow up on {draft_type} sent to {recipient}: {subject[:60]}",
                "draft-send",
                "Open",
                followup_due,
                f"Auto-created follow-up for sent draft {request.draft_id}. Check if {recipient} responded.",
                timestamp,
                timestamp,
            ),
        )

        response = {
            "ok": True,
            "draft": dict(
                conn.execute(
                    "SELECT * FROM drafts WHERE id = ?", (request.draft_id,)
                ).fetchone()
            ),
            "followup": dict(
                conn.execute(
                    "SELECT * FROM followups WHERE id = ?", (followup_id,)
                ).fetchone()
            ),
            "already_sent": False,
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
