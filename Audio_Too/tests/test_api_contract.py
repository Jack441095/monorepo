"""Versioned API contract and typed schema tests."""

from __future__ import annotations

import pytest

from app import api_contract
from app.api_schemas import (
    AutomixRevisionRequest,
    AutomixStartRequest,
    DraftDeliveryRequest,
    DraftSendRequest,
    EnquiryConversionRequest,
    LeadConversionRequest,
    SchemaValidationError,
)
from app.routes.api_contract_routes import handle_api_contract_get


class Handler:
    def __init__(self) -> None:
        self.status = 0
        self.payload: dict = {}

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload


def test_versioned_aliases_preserve_query_data() -> None:
    assert (
        api_contract.dispatch_path("GET", "/api/v1/automix/jobs?id=job-1")
        == "/api/automix/status?id=job-1"
    )
    assert api_contract.dispatch_path("POST", "/api/v1/automix/jobs") == "/api/automix/start"
    assert (
        api_contract.dispatch_path("GET", "/api/v1/automix/queue-health")
        == "/api/automix/queue-health"
    )
    assert (
        api_contract.dispatch_path("POST", "/api/v1/automix/uploads")
        == "/api/automix/upload"
    )
    assert (
        api_contract.dispatch_path("POST", "/api/v1/automix/revisions")
        == "/api/automix/revise"
    )
    assert (
        api_contract.dispatch_path(
            "POST", "/api/v1/business/enquiries/conversions"
        )
        == "/api/admin/enquiries/convert"
    )
    assert (
        api_contract.dispatch_path("POST", "/api/v1/business/leads/conversions")
        == "/api/admin/leads/convert"
    )
    assert (
        api_contract.dispatch_path("POST", "/api/v1/business/drafts/sends")
        == "/api/admin/drafts/send"
    )
    assert (
        api_contract.dispatch_path(
            "GET", "/api/v1/business/draft-deliveries?id=delivery-1"
        )
        == "/api/admin/draft-deliveries/status?id=delivery-1"
    )
    assert (
        api_contract.dispatch_path("POST", "/api/v1/business/draft-deliveries")
        == "/api/admin/draft-deliveries"
    )
    assert (
        api_contract.legacy_successor("POST", "/api/automix/start")
        == "/api/v1/automix/jobs"
    )
    assert (
        api_contract.legacy_successor("POST", "/api/automix/upload")
        == "/api/v1/automix/uploads"
    )
    assert (
        api_contract.dispatch_path("POST", "/api/v1/automix/advisor-feedback")
        == "/api/automix/advisor-feedback"
    )
    assert (
        api_contract.legacy_successor("POST", "/api/automix/advisor-feedback/delete")
        == "/api/v1/automix/advisor-feedback/deletions"
    )
    assert (
        api_contract.dispatch_path(
            "POST", "/api/v1/automix/musical-role-corrections/deletions"
        )
        == "/api/automix/musical-role-corrections/delete"
    )
    assert (
        api_contract.legacy_successor("POST", "/api/admin/enquiries/convert")
        == "/api/v1/business/enquiries/conversions"
    )
    assert (
        api_contract.legacy_successor("POST", "/api/admin/leads/convert")
        == "/api/v1/business/leads/conversions"
    )
    assert (
        api_contract.legacy_successor("POST", "/api/admin/drafts/send")
        == "/api/v1/business/drafts/sends"
    )
    assert (
        api_contract.legacy_successor("POST", "/api/admin/draft-deliveries")
        == "/api/v1/business/draft-deliveries"
    )
    assert "2027" in api_contract.LEGACY_API_SUNSET


def test_openapi_document_describes_versioned_routes_and_errors() -> None:
    document = api_contract.openapi_document()
    assert document["openapi"] == "3.1.0"
    assert document["info"]["version"] == api_contract.API_VERSION
    assert set(document["paths"]) == {
        "/api/v1/automix/jobs",
        "/api/v1/automix/queue-health",
        "/api/v1/automix/revisions",
        "/api/v1/automix/uploads",
        "/api/v1/automix/advisor-feedback",
        "/api/v1/automix/advisor-feedback/deletions",
        "/api/v1/automix/musical-role-corrections/deletions",
        "/api/v1/automix/advisor-previews/{artifact_id}",
        "/api/v1/business/enquiries/conversions",
        "/api/v1/business/leads/conversions",
        "/api/v1/business/drafts/sends",
        "/api/v1/business/draft-deliveries",
    }
    error = document["components"]["schemas"]["ApiError"]
    assert error["required"] == ["error", "code", "message", "details", "request_id"]
    feedback = document["components"]["schemas"]["AutomixAdvisorFeedbackRequest"]
    assert feedback["additionalProperties"] is False
    assert "audible_improvement_rating" not in feedback["required"]
    assert {choice["type"] for choice in feedback["properties"]["audible_improvement_rating"]["oneOf"]} == {
        "integer",
        "null",
    }

    handler = Handler()
    assert handle_api_contract_get(handler, "/api/v1/openapi.json")
    assert handler.status == 200
    assert handler.payload == document


def test_automix_start_schema_is_typed_and_bounded() -> None:
    request = AutomixStartRequest.from_payload(
        {"project_id": "project-1", "genre": "pop", "style_prefs": {"warmth": 0.7}}
    )
    assert request.project_id == "project-1"
    assert request.style_prefs == {"warmth": 0.7}

    with pytest.raises(SchemaValidationError, match="style_prefs must be"):
        AutomixStartRequest.from_payload(
            {"project_id": "project-1", "style_prefs": ["not", "an", "object"]}
        )
    with pytest.raises(SchemaValidationError, match="Unknown request field"):
        AutomixStartRequest.from_payload({"project_id": "project-1", "unexpected": True})


def test_automix_start_schema_accepts_and_bounds_correlation_id() -> None:
    request = AutomixStartRequest.from_payload(
        {"project_id": "project-1", "correlation_id": "thursday-cmd:abc123"}
    )
    assert request.correlation_id == "thursday-cmd:abc123"

    default_request = AutomixStartRequest.from_payload({"project_id": "project-1"})
    assert default_request.correlation_id == ""

    with pytest.raises(SchemaValidationError, match="correlation_id must be"):
        AutomixStartRequest.from_payload(
            {"project_id": "project-1", "correlation_id": "x" * 201}
        )


def test_automix_revision_schema_requires_bounded_feedback() -> None:
    request = AutomixRevisionRequest.from_payload(
        {"project_id": "project-1", "feedback": "More vocal presence"}
    )
    assert request.feedback == "More vocal presence"

    with pytest.raises(SchemaValidationError, match="feedback is required"):
        AutomixRevisionRequest.from_payload({"project_id": "project-1", "feedback": " "})


def test_enquiry_conversion_schema_accepts_only_a_safe_id() -> None:
    request = EnquiryConversionRequest.from_payload({"id": "enquiry-1"})
    assert request.enquiry_id == "enquiry-1"

    with pytest.raises(SchemaValidationError, match="Unknown request field"):
        EnquiryConversionRequest.from_payload({"id": "enquiry-1", "name": "Sam"})
    with pytest.raises(SchemaValidationError, match="enquiry ID"):
        EnquiryConversionRequest.from_payload({"id": "../../escape"})


def test_lead_conversion_schema_accepts_only_a_safe_id() -> None:
    request = LeadConversionRequest.from_payload({"id": "lead-1"})
    assert request.lead_id == "lead-1"

    with pytest.raises(SchemaValidationError, match="Unknown request field"):
        LeadConversionRequest.from_payload({"id": "lead-1", "force": True})
    with pytest.raises(SchemaValidationError, match="lead ID"):
        LeadConversionRequest.from_payload({"id": "../../escape"})


def test_draft_send_schema_accepts_only_a_safe_id() -> None:
    request = DraftSendRequest.from_payload({"id": "draft-1"})
    assert request.draft_id == "draft-1"

    with pytest.raises(SchemaValidationError, match="Unknown request field"):
        DraftSendRequest.from_payload({"id": "draft-1", "force": True})
    with pytest.raises(SchemaValidationError, match="draft ID"):
        DraftSendRequest.from_payload({"id": "../../escape"})


def test_draft_delivery_schema_requires_a_safe_id_and_email() -> None:
    request = DraftDeliveryRequest.from_payload(
        {"id": "draft-1", "recipient_email": "Artist@Example.com"}
    )
    assert request.draft_id == "draft-1"
    assert request.recipient_email == "artist@example.com"

    with pytest.raises(SchemaValidationError, match="valid recipient_email"):
        DraftDeliveryRequest.from_payload(
            {"id": "draft-1", "recipient_email": "not-an-email"}
        )
