"""Tests for enquiry storage and CRM conversion."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import db  # noqa: E402
import enquiries  # noqa: E402
import enquiry_service  # noqa: E402
import idempotency  # noqa: E402
from app import api_contract  # noqa: E402
from app.api_schemas import EnquiryConversionRequest  # noqa: E402
from app.routes.admin_routes import handle_admin_post  # noqa: E402


@pytest.fixture()
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "empty-agent-data")
    monkeypatch.setattr(db, "_migration_done", False)
    db.init_db()
    yield db_path


def test_create_and_convert_enquiry(temp_db: Path) -> None:
    enquiry = enquiries.create_enquiry(
        {
            "name": "Sam Artist",
            "email": "sam@example.com",
            "service": "Mixing",
            "message": "Need a mix for an EP with a tight deadline and clear references.",
            "deadline": "July",
        }
    )
    assert enquiry["status"] == "New"
    result = enquiries.convert_enquiry_to_crm(str(enquiry["id"]))
    assert result is not None
    assert result["client"]["name"] == "Sam Artist"
    assert result["lead"]["score"] >= 70
    assert result["enquiry"]["status"] == "Converted"
    again = enquiries.convert_enquiry_to_crm(str(enquiry["id"]))
    assert again is not None
    assert again.get("already_converted")


def make_enquiry(name: str = "Sam Artist") -> dict:
    return enquiries.create_enquiry(
        {
            "name": name,
            "email": f"{name.lower().replace(' ', '.')}@example.com",
            "service": "Mixing",
            "message": "Please mix this release with clear references and preserved dynamics.",
            "deadline": "July",
        }
    )


def test_conversion_service_replays_without_duplicate_records(temp_db: Path) -> None:
    enquiry = make_enquiry()
    request = EnquiryConversionRequest.from_payload({"id": enquiry["id"]})

    first = enquiry_service.convert_enquiry(request, idempotency_key="convert-1")
    replay = enquiry_service.convert_enquiry(request, idempotency_key="convert-1")

    assert replay == first
    assert len(db.list_records("clients")) == 1
    assert len(db.list_records("projects")) == 1
    assert len(db.list_records("leads")) == 1


def test_conversion_service_rejects_key_reuse_for_another_enquiry(temp_db: Path) -> None:
    first = make_enquiry("First Artist")
    second = make_enquiry("Second Artist")
    enquiry_service.convert_enquiry(
        EnquiryConversionRequest.from_payload({"id": first["id"]}),
        idempotency_key="shared-key",
    )

    with pytest.raises(idempotency.IdempotencyConflict):
        enquiry_service.convert_enquiry(
            EnquiryConversionRequest.from_payload({"id": second["id"]}),
            idempotency_key="shared-key",
        )


def test_already_converted_service_result_does_not_duplicate_records(temp_db: Path) -> None:
    enquiry = make_enquiry()
    request = EnquiryConversionRequest.from_payload({"id": enquiry["id"]})
    enquiry_service.convert_enquiry(request)

    status, result = enquiry_service.convert_enquiry(
        request, idempotency_key="already-converted"
    )

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


def test_versioned_conversion_route_uses_typed_retry_safe_service(temp_db: Path) -> None:
    enquiry = make_enquiry()
    path = api_contract.dispatch_path(
        "POST", "/api/v1/business/enquiries/conversions"
    )
    first = RouteHandler({"id": enquiry["id"]}, "route-convert-1")
    replay = RouteHandler({"id": enquiry["id"]}, "route-convert-1")

    assert handle_admin_post(first, path, log_event=lambda *_args: None)
    assert handle_admin_post(replay, path, log_event=lambda *_args: None)

    assert first.status == 200
    assert replay.response == first.response
    assert first.response["client"]["name"] == "Sam Artist"
    assert len(db.list_records("clients")) == 1
