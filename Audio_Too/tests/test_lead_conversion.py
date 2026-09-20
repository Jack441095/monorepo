"""Transactional lead conversion service, API, and Thursday integration tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app import api_contract
from app.api_schemas import LeadConversionRequest
from app.routes.admin_routes import handle_admin_post
from agents.Shared import workflow

import db
import idempotency
import lead_service


@pytest.fixture()
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "lead.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "empty-agent-data")
    monkeypatch.setattr(db, "_migration_done", False)
    db.init_db()
    return db_path


def make_lead(name: str = "Jordan", status: str = "Warm") -> dict:
    return db.add_record(
        "leads",
        {
            "lead": name,
            "contact": f"{name.lower()}@example.com",
            "type": "referral",
            "service_fit": "Mixing",
            "status": status,
            "score": 85,
            "source": "referral",
            "next_action": "Qualify",
            "waiting_on": "Reply",
            "follow_up": "2026-07-10",
        },
    )


def request_for(lead: dict) -> LeadConversionRequest:
    return LeadConversionRequest.from_payload({"id": lead["id"]})


def test_lead_conversion_is_atomic_and_replay_safe(temp_db: Path) -> None:
    lead = make_lead()
    request = request_for(lead)

    first = lead_service.convert_lead(request, idempotency_key="lead-convert-1")
    replay = lead_service.convert_lead(request, idempotency_key="lead-convert-1")

    assert replay == first
    assert first[1]["lead"]["status"] == "Converted"
    assert first[1]["client"]["name"] == "Jordan"
    assert first[1]["project"]["service"] == "Mixing"
    assert len(db.list_records("clients")) == 1
    assert len(db.list_records("projects")) == 1


def test_lead_conversion_rolls_back_all_records_on_project_failure(temp_db: Path) -> None:
    lead = make_lead()
    with db.connect() as conn:
        conn.execute(
            """CREATE TRIGGER reject_project BEFORE INSERT ON projects
               BEGIN SELECT RAISE(ABORT, 'project rejected'); END"""
        )
        conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        lead_service.convert_lead(request_for(lead))

    assert db.list_records("clients") == []
    assert db.list_records("projects") == []
    assert db.list_records("leads")[0]["status"] == "Warm"


def test_lead_conversion_rejects_key_reuse_for_another_lead(temp_db: Path) -> None:
    first = make_lead("Jordan")
    second = make_lead("Morgan")
    lead_service.convert_lead(
        request_for(first), idempotency_key="shared-lead-key"
    )

    with pytest.raises(idempotency.IdempotencyConflict):
        lead_service.convert_lead(
            request_for(second), idempotency_key="shared-lead-key"
        )


def test_closed_lead_is_not_convertible(temp_db: Path) -> None:
    lead = make_lead(status="Closed")
    with pytest.raises(lead_service.LeadNotConvertible):
        lead_service.convert_lead(request_for(lead))
    assert db.list_records("clients") == []


def test_already_converted_lead_does_not_duplicate_records(temp_db: Path) -> None:
    lead = make_lead()
    request = request_for(lead)
    lead_service.convert_lead(request)

    status, result = lead_service.convert_lead(request)

    assert status == 200
    assert result["already_converted"] is True
    assert result["client"] is None
    assert len(db.list_records("clients")) == 1


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


def test_versioned_lead_conversion_route_replays_response(temp_db: Path) -> None:
    lead = make_lead()
    path = api_contract.dispatch_path(
        "POST", "/api/v1/business/leads/conversions"
    )
    first = RouteHandler({"id": lead["id"]}, "route-lead-convert-1")
    replay = RouteHandler({"id": lead["id"]}, "route-lead-convert-1")

    assert handle_admin_post(first, path, log_event=lambda *_args: None)
    assert handle_admin_post(replay, path, log_event=lambda *_args: None)
    assert first.status == 200
    assert replay.response == first.response
    assert len(db.list_records("clients")) == 1


def test_thursday_lead_conversion_resolves_name_and_uses_service(
    temp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_lead("Jordan")
    events = []
    monkeypatch.setattr(workflow, "log_event", lambda *args, **kwargs: events.append((args, kwargs)))

    result = workflow.convert_lead_to_client_and_project(
        db.list_records, db.add_record, "jordan"
    )

    assert result["ok"] is True
    assert result["client"]["name"] == "Jordan"
    assert db.list_records("leads")[0]["status"] == "Converted"
    assert len(events) == 1
