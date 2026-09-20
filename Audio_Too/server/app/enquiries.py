"""Website enquiry records and optional CRM conversion."""

from __future__ import annotations

from app.api_schemas import EnquiryConversionRequest
from enquiry_service import EnquiryNotFound, convert_enquiry, score_enquiry as _score_enquiry
from db import add_record


def score_enquiry(service: str, message: str, deadline: str) -> int:
    """Compatibility export for callers of the legacy enquiry module."""
    return _score_enquiry(service, message, deadline)


def create_enquiry(clean: dict) -> dict:
    return add_record(
        "enquiries",
        {
            "name": clean["name"],
            "email": clean["email"],
            "service": clean["service"],
            "message": clean["message"],
            "deadline": clean["deadline"],
            "status": "New",
        },
    )


def convert_enquiry_to_crm(enquiry_id: str) -> dict | None:
    """Compatibility wrapper for older callers of the enquiry module."""
    try:
        request = EnquiryConversionRequest.from_payload({"id": enquiry_id})
        _status, result = convert_enquiry(request)
        return result
    except EnquiryNotFound:
        return None
