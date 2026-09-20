"""Claim and deliver durable outbox email jobs with explicit receipt states."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from uuid import uuid4

from app import email_notify
from db import connect, now

DELIVERY_LEASE_SECONDS = 90


def _future_timestamp(seconds: int) -> str:
    return (datetime.now() + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")


def recover_abandoned_deliveries() -> dict:
    """Requeue pre-send claims and quarantine deliveries abandoned after SMTP began."""
    timestamp = now()
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        requeued = conn.execute(
            """UPDATE delivery_outbox
               SET status = 'queued', worker_id = NULL, claimed_at = NULL,
                   lease_expiry_at = NULL, updated_at = ?
               WHERE status = 'claimed' AND lease_expiry_at < ?""",
            (timestamp, timestamp),
        ).rowcount
        uncertain_rows = conn.execute(
            """SELECT id, aggregate_type, aggregate_id FROM delivery_outbox
               WHERE status = 'sending' AND lease_expiry_at < ?""",
            (timestamp,),
        ).fetchall()
        for row in uncertain_rows:
            conn.execute(
                """UPDATE delivery_outbox
                   SET status = 'uncertain', worker_id = NULL, lease_expiry_at = NULL,
                       last_error = 'Worker stopped after SMTP delivery began; verify before retrying.',
                       updated_at = ? WHERE id = ?""",
                (timestamp, row["id"]),
            )
            if row["aggregate_type"] == "draft":
                conn.execute(
                    """UPDATE drafts SET status = 'Delivery uncertain',
                       optimistic_version = COALESCE(optimistic_version, 1) + 1,
                       updated_at = ? WHERE id = ?""",
                    (timestamp, row["aggregate_id"]),
                )
        conn.commit()
    return {"requeued": requeued, "uncertain": len(uncertain_rows)}


def claim_next_delivery(worker_id: str) -> dict | None:
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT id FROM delivery_outbox
               WHERE status = 'queued' ORDER BY created_at, rowid LIMIT 1"""
        ).fetchone()
        if not row:
            return None
        timestamp = now()
        updated = conn.execute(
            """UPDATE delivery_outbox
               SET status = 'claimed', attempts = attempts + 1, worker_id = ?,
                   claimed_at = ?, lease_expiry_at = ?, updated_at = ?
               WHERE id = ? AND status = 'queued'""",
            (
                worker_id,
                timestamp,
                _future_timestamp(DELIVERY_LEASE_SECONDS),
                timestamp,
                row["id"],
            ),
        )
        if updated.rowcount != 1:
            conn.rollback()
            return None
        claimed = conn.execute(
            "SELECT * FROM delivery_outbox WHERE id = ?", (row["id"],)
        ).fetchone()
        conn.commit()
    return dict(claimed)


def mark_sending(delivery_id: str, worker_id: str) -> None:
    timestamp = now()
    with connect() as conn:
        updated = conn.execute(
            """UPDATE delivery_outbox
               SET status = 'sending', sending_at = ?, lease_expiry_at = ?, updated_at = ?
               WHERE id = ? AND status = 'claimed' AND worker_id = ?""",
            (
                timestamp,
                _future_timestamp(DELIVERY_LEASE_SECONDS),
                timestamp,
                delivery_id,
                worker_id,
            ),
        )
        conn.commit()
    if updated.rowcount != 1:
        raise RuntimeError("Delivery claim was lost before SMTP began.")


def complete_delivery(delivery_id: str, provider_receipt: str) -> dict:
    timestamp = now()
    followup_due = (date.today() + timedelta(days=7)).isoformat()
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM delivery_outbox WHERE id = ?", (delivery_id,)
        ).fetchone()
        if not row:
            raise KeyError(f"Delivery not found: {delivery_id}")
        delivery = dict(row)
        if delivery["status"] == "sent":
            conn.commit()
            return delivery
        if delivery["status"] != "sending":
            raise RuntimeError(f"Cannot complete delivery from {delivery['status']} state.")

        followup_id = None
        if delivery["aggregate_type"] == "draft":
            followup_id = str(uuid4())[:8]
            conn.execute(
                """INSERT INTO followups
                   (id, owner, subject, source, status, due, notes, created_at, updated_at)
                   VALUES (?, 'delivery-worker', ?, 'external-delivery', 'Open', ?, ?, ?, ?)""",
                (
                    followup_id,
                    f"Follow up after email delivery to {delivery['recipient']}: {delivery['subject'][:60]}",
                    followup_due,
                    f"Auto-created from delivery {delivery_id} for draft {delivery['aggregate_id']}.",
                    timestamp,
                    timestamp,
                ),
            )
        conn.execute(
            """UPDATE delivery_outbox
               SET status = 'sent', sent_at = ?, provider_receipt = ?, followup_id = ?,
                   worker_id = NULL, lease_expiry_at = NULL, last_error = '', updated_at = ?
               WHERE id = ? AND status = 'sending'""",
            (timestamp, provider_receipt, followup_id, timestamp, delivery_id),
        )
        if delivery["aggregate_type"] == "draft":
            conn.execute(
                """UPDATE drafts SET status = 'Sent',
                   optimistic_version = COALESCE(optimistic_version, 1) + 1,
                   updated_at = ? WHERE id = ?""",
                (timestamp, delivery["aggregate_id"]),
            )
        completed = conn.execute(
            "SELECT * FROM delivery_outbox WHERE id = ?", (delivery_id,)
        ).fetchone()
        conn.commit()
    return dict(completed)


def mark_uncertain(delivery_id: str, error: Exception) -> None:
    timestamp = now()
    safe_error = f"{error.__class__.__name__}: delivery outcome requires review."
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT aggregate_type, aggregate_id FROM delivery_outbox WHERE id = ?",
            (delivery_id,),
        ).fetchone()
        conn.execute(
            """UPDATE delivery_outbox
               SET status = 'uncertain', worker_id = NULL, lease_expiry_at = NULL,
                   last_error = ?, updated_at = ?
               WHERE id = ? AND status IN ('claimed', 'sending')""",
            (safe_error, timestamp, delivery_id),
        )
        if row and row["aggregate_type"] == "draft":
            conn.execute(
                """UPDATE drafts SET status = 'Delivery uncertain',
                   optimistic_version = COALESCE(optimistic_version, 1) + 1,
                   updated_at = ? WHERE id = ?""",
                (timestamp, row["aggregate_id"]),
            )
        conn.commit()


def process_one(
    worker_id: str,
    *,
    send_func=None,
    enabled_func=None,
) -> dict | None:
    """Process at most one delivery; disabled policy leaves the queue untouched."""
    enabled = enabled_func or email_notify.smtp_delivery_enabled
    if not enabled():
        return None
    delivery = claim_next_delivery(worker_id)
    if not delivery:
        return None
    sender = send_func or email_notify.send_email
    try:
        mark_sending(delivery["id"], worker_id)
        payload = json.loads(delivery["payload_json"])
        receipt = sender(
            to=delivery["recipient"],
            subject=delivery["subject"],
            text_body=str(payload.get("text_body", "")),
        )
        return complete_delivery(delivery["id"], receipt)
    except Exception as exc:
        mark_uncertain(delivery["id"], exc)
        return None
