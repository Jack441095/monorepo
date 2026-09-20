"""Durable external-delivery queue, worker, and API tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import api_contract
from app.api_schemas import DraftDeliveryRequest
from app.routes.admin_routes import handle_admin_get, handle_admin_post

import db
import delivery_service
import delivery_worker
import idempotency
import notify


@pytest.fixture()
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "delivery.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "empty-agent-data")
    monkeypatch.setattr(db, "_migration_done", False)
    db.init_db()
    return db_path


def make_approved_draft() -> dict:
    return db.add_record(
        "drafts",
        {
            "type": "email",
            "recipient": "Jordan",
            "subject": "Mix update",
            "body": "The reviewed mix is ready.",
            "status": "Approved",
            "source": "test",
        },
    )


def request_for(draft: dict, email: str = "jordan@example.com") -> DraftDeliveryRequest:
    return DraftDeliveryRequest.from_payload(
        {"id": draft["id"], "recipient_email": email}
    )


def outbox_rows() -> list[dict]:
    with db.connect() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM delivery_outbox")]


def test_queue_is_transactional_and_idempotent(temp_db: Path) -> None:
    draft = make_approved_draft()
    request = request_for(draft)

    first = delivery_service.queue_draft_delivery(
        request, idempotency_key="delivery-create-1"
    )
    replay = delivery_service.queue_draft_delivery(
        request, idempotency_key="delivery-create-1"
    )

    assert first == replay
    assert first[0] == 202
    assert first[1]["delivery"]["status"] == "queued"
    assert len(outbox_rows()) == 1
    assert db.list_records("drafts")[0]["status"] == "Delivery queued"


def test_queue_rejects_idempotency_key_reuse_with_changed_recipient(temp_db: Path) -> None:
    draft = make_approved_draft()
    delivery_service.queue_draft_delivery(
        request_for(draft), idempotency_key="same-delivery-key"
    )

    with pytest.raises(idempotency.IdempotencyConflict):
        delivery_service.queue_draft_delivery(
            request_for(draft, "other@example.com"),
            idempotency_key="same-delivery-key",
        )


def test_disabled_policy_leaves_queue_untouched(temp_db: Path) -> None:
    draft = make_approved_draft()
    delivery_service.queue_draft_delivery(request_for(draft))

    assert delivery_worker.process_one(
        "worker-1", enabled_func=lambda: False
    ) is None
    row = outbox_rows()[0]
    assert row["status"] == "queued"
    assert row["attempts"] == 0


def test_worker_records_receipt_and_followup_after_send(temp_db: Path) -> None:
    draft = make_approved_draft()
    _status, queued = delivery_service.queue_draft_delivery(request_for(draft))
    sent_payloads: list[dict] = []

    def send(**payload):
        sent_payloads.append(payload)
        return "<provider-receipt@example.com>"

    result = delivery_worker.process_one(
        "worker-1", send_func=send, enabled_func=lambda: True
    )

    assert result is not None
    assert result["id"] == queued["delivery"]["id"]
    assert result["status"] == "sent"
    assert result["provider_receipt"] == "<provider-receipt@example.com>"
    assert sent_payloads == [{
        "to": "jordan@example.com",
        "subject": "Mix update",
        "text_body": "The reviewed mix is ready.",
    }]
    assert db.list_records("drafts")[0]["status"] == "Sent"
    assert len(db.list_records("followups")) == 1


def test_worker_quarantines_uncertain_outcome_without_followup(temp_db: Path) -> None:
    draft = make_approved_draft()
    delivery_service.queue_draft_delivery(request_for(draft))

    def fail(**_payload):
        raise OSError("private provider detail")

    assert delivery_worker.process_one(
        "worker-1", send_func=fail, enabled_func=lambda: True
    ) is None
    row = outbox_rows()[0]
    assert row["status"] == "uncertain"
    assert "private provider detail" not in row["last_error"]
    assert db.list_records("drafts")[0]["status"] == "Delivery uncertain"
    assert db.list_records("followups") == []


def test_new_enquiry_email_notification_uses_outbox(
    temp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(notify, "notifications_enabled", lambda: False)
    monkeypatch.setattr(notify, "email_enabled", lambda: True)
    monkeypatch.setattr(
        notify, "smtp_settings", lambda: {"to": "owner@example.com"}
    )

    notify.notify_new_enquiry(
        "Jordan",
        "Mixing",
        email="jordan@example.com",
        message="Please review my new mix enquiry.",
        deadline="Friday",
        client_id="enquiry1",
    )

    row = outbox_rows()[0]
    assert row["aggregate_type"] == "enquiry"
    assert row["aggregate_id"] == "enquiry1"
    assert row["recipient"] == "owner@example.com"

    result = delivery_worker.process_one(
        "worker-1",
        send_func=lambda **_payload: "<enquiry-receipt@example.com>",
        enabled_func=lambda: True,
    )
    assert result is not None
    assert result["status"] == "sent"
    assert db.list_records("followups") == []


def test_automix_ready_notification_uses_outbox_without_followup(temp_db: Path) -> None:
    delivery = delivery_service.queue_automix_notification(
        job_id="job12345",
        project_id="project1",
        destination="artist@example.com",
        version=2,
        download_url="http://127.0.0.1:8080/api/automix/download/project1",
    )
    assert delivery["aggregate_type"] == "automix_job"
    assert delivery["status"] == "queued"

    result = delivery_worker.process_one(
        "worker-1",
        send_func=lambda **_payload: "<mix-receipt@example.com>",
        enabled_func=lambda: True,
    )
    assert result is not None
    assert result["status"] == "sent"
    assert result["provider_receipt"] == "<mix-receipt@example.com>"
    assert db.list_records("followups") == []


def test_recovery_requeues_claims_but_quarantines_started_sends(temp_db: Path) -> None:
    first = make_approved_draft()
    second = make_approved_draft()
    delivery_service.queue_draft_delivery(request_for(first, "first@example.com"))
    delivery_service.queue_draft_delivery(request_for(second, "second@example.com"))
    rows = outbox_rows()
    with db.connect() as conn:
        conn.execute(
            """UPDATE delivery_outbox SET status = 'claimed', lease_expiry_at = '2000-01-01 00:00:00'
               WHERE id = ?""",
            (rows[0]["id"],),
        )
        conn.execute(
            """UPDATE delivery_outbox SET status = 'sending', lease_expiry_at = '2000-01-01 00:00:00'
               WHERE id = ?""",
            (rows[1]["id"],),
        )
        conn.commit()

    recovered = delivery_worker.recover_abandoned_deliveries()
    statuses = sorted(row["status"] for row in outbox_rows())
    assert recovered == {"requeued": 1, "uncertain": 1}
    assert statuses == ["queued", "uncertain"]


class RouteHandler:
    def __init__(self, payload: dict | None = None, key: str = "") -> None:
        self.payload = payload or {}
        self.headers = {"Idempotency-Key": key} if key else {}
        self.status = 0
        self.response: dict = {}

    def read_json_body(self) -> dict:
        return self.payload

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.response = payload


def test_versioned_queue_and_status_routes_share_outbox_service(temp_db: Path) -> None:
    draft = make_approved_draft()
    post_path = api_contract.dispatch_path(
        "POST", "/api/v1/business/draft-deliveries"
    )
    post = RouteHandler(
        {"id": draft["id"], "recipient_email": "jordan@example.com"},
        "route-delivery-1",
    )
    assert handle_admin_post(post, post_path, log_event=lambda *_args: None)
    assert post.status == 202

    delivery_id = post.response["delivery"]["id"]
    get_path = api_contract.dispatch_path(
        "GET", f"/api/v1/business/draft-deliveries?id={delivery_id}"
    )
    get = RouteHandler()
    assert handle_admin_get(get, get_path)
    assert get.status == 200
    assert get.response["delivery"]["id"] == delivery_id
