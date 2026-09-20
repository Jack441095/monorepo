"""Transactional and HTTP contract tests for draft sends."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import api_contract
from app.api_schemas import DraftSendRequest
from app.routes.admin_routes import handle_admin_post

import db
import draft_service
import idempotency


@pytest.fixture()
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "empty-agent-data")
    monkeypatch.setattr(db, "_migration_done", False)
    db.init_db()
    return db_path


def make_draft(recipient: str = "Jordan", status: str = "Approved") -> dict:
    return db.add_record(
        "drafts",
        {
            "type": "invoice",
            "recipient": recipient,
            "subject": "Mix invoice",
            "body": "Invoice attached",
            "status": status,
            "source": "test",
        },
    )


def test_draft_send_is_atomic_and_replay_safe(temp_db: Path) -> None:
    draft = make_draft()
    request = DraftSendRequest.from_payload({"id": draft["id"]})

    first = draft_service.send_draft(request, idempotency_key="draft-send-1")
    replay = draft_service.send_draft(request, idempotency_key="draft-send-1")

    assert replay == first
    assert first[1]["draft"]["status"] == "Sent"
    assert first[1]["followup"]["owner"] == "draft-sender"
    assert len(db.list_records("followups")) == 1


def test_draft_send_rejects_key_reuse_for_another_draft(temp_db: Path) -> None:
    first = make_draft("Jordan")
    second = make_draft("Morgan")
    draft_service.send_draft(
        DraftSendRequest.from_payload({"id": first["id"]}),
        idempotency_key="shared-send-key",
    )

    with pytest.raises(idempotency.IdempotencyConflict):
        draft_service.send_draft(
            DraftSendRequest.from_payload({"id": second["id"]}),
            idempotency_key="shared-send-key",
        )


def test_already_sent_draft_does_not_create_another_followup(temp_db: Path) -> None:
    draft = make_draft()
    request = DraftSendRequest.from_payload({"id": draft["id"]})
    draft_service.send_draft(request)

    status, result = draft_service.send_draft(request)

    assert status == 200
    assert result["already_sent"] is True
    assert result["followup"] is None
    assert len(db.list_records("followups")) == 1


def test_rejected_draft_is_not_sendable(temp_db: Path) -> None:
    draft = make_draft(status="Rejected")
    with pytest.raises(draft_service.DraftNotSendable):
        draft_service.send_draft(
            DraftSendRequest.from_payload({"id": draft["id"]})
        )
    assert db.list_records("followups") == []


class RouteHandler:
    def __init__(self, payload: dict, key: str = "") -> None:
        self.payload = payload
        self.headers = {"Idempotency-Key": key} if key else {}
        self.status = 0
        self.response: dict = {}

    def read_json_body(self) -> dict:
        return self.payload

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.response = payload


def test_versioned_draft_send_route_replays_original_response(temp_db: Path) -> None:
    draft = make_draft()
    path = api_contract.dispatch_path("POST", "/api/v1/business/drafts/sends")
    first = RouteHandler({"id": draft["id"]}, "route-draft-send-1")
    replay = RouteHandler({"id": draft["id"]}, "route-draft-send-1")

    assert handle_admin_post(first, path, log_event=lambda *_args: None)
    assert handle_admin_post(replay, path, log_event=lambda *_args: None)

    assert first.status == 200
    assert replay.response == first.response
    assert len(db.list_records("followups")) == 1
