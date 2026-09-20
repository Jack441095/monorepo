"""Cross-domain business integration: draft creation → approval → delivery.

Unit tests cover each service in isolation; this exercises the real chain end to
end — `draft_service.create_draft` → `status_transition_service.transition_status`
→ `delivery_service.queue_draft_delivery` — and asserts the durable domain-event
stream records the whole journey in order. This is the cross-service path the
per-service tests miss.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BUSINESS_APP = Path(__file__).resolve().parent.parent / "server" / "app"
if str(BUSINESS_APP) not in sys.path:
    sys.path.insert(0, str(BUSINESS_APP))

import db  # noqa: E402
import delivery_service  # noqa: E402
import draft_service  # noqa: E402
import status_transition_service as sts  # noqa: E402
from api_schemas import DraftCreateRequest, DraftDeliveryRequest  # noqa: E402


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy")
    monkeypatch.setattr(db, "_migration_done", False)
    db.init_db()
    return db


def _all_events() -> list[dict]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT event_type, aggregate_type, aggregate_id FROM domain_events ORDER BY occurred_at, rowid"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _outbox_for(draft_id: str) -> list[dict]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM delivery_outbox WHERE aggregate_id = ?", (draft_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def test_draft_creation_approval_delivery_chain(temp_db):
    # 1. Draft created (Pending) via the typed create service.
    _, created = draft_service.create_draft(
        DraftCreateRequest.from_payload({
            "type": "email",
            "recipient": "Jordan",
            "subject": "Your mix is ready",
            "body": "Here is the reviewed mix.",
            "source": "integration",
        })
    )
    draft_id = created["draft"]["id"]
    assert created["draft"]["status"] == "Pending"

    # 2. Draft approved via the status-transition service (optimistic version + event).
    approved = sts.transition_status(
        sts.StatusTransitionRequest.from_payload(
            {"table": "drafts", "id": draft_id, "status": "Approved"}
        )
    )
    assert approved["status"] == "Approved"

    # 3. Delivery queued via the durable outbox service.
    status_code, delivery = delivery_service.queue_draft_delivery(
        DraftDeliveryRequest.from_payload({"id": draft_id, "recipient_email": "jordan@example.com"})
    )
    assert status_code == 202  # accepted into the durable outbox for async send
    outbox = _outbox_for(draft_id)
    assert len(outbox) == 1  # exactly one durable delivery record queued

    # 4. The event stream recorded the cross-service journey, in order.
    events = _all_events()
    types = [e["event_type"] for e in events]
    assert "draft.created" in types
    assert "record.status_changed" in types
    assert types.index("draft.created") < types.index("record.status_changed")

    # The status-change event is attributed to the drafts aggregate.
    status_events = [e for e in events if e["event_type"] == "record.status_changed"]
    assert status_events and status_events[0]["aggregate_id"] == draft_id


def test_delivery_requires_a_persisted_draft(temp_db):
    # Cross-service guard: you cannot queue delivery for a draft that never existed.
    with pytest.raises(Exception):
        delivery_service.queue_draft_delivery(
            DraftDeliveryRequest.from_payload({"id": "ghost123", "recipient_email": "x@y.com"})
        )
