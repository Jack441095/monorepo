from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .database import get_db
from .email import send_email
from .email_templates import _SIGNOFF
from .rate_limit import rate_limit

logger = logging.getLogger("nitedsp.contact")

router = APIRouter(prefix="/contact", tags=["contact"])


class ContactRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(None, max_length=30)
    message: str = Field(..., min_length=1, max_length=2000)


class ContactResponse(BaseModel):
    ok: bool
    message: str


def _build_contact_email(body: ContactRequest) -> tuple[str, str]:
    body_text = (
        f"New contact form submission\n\n"
        f"Name: {body.name}\n"
        f"Email: {body.email}\n"
        f"Phone: {body.phone or 'Not provided'}\n\n"
        f"Message:\n{body.message}\n\n"
        f"This enquiry was submitted via the website contact form."
        + _SIGNOFF
    )
    return "New website enquiry", body_text


@router.post("/submit", response_model=ContactResponse)
async def submit_contact(
    body: ContactRequest,
    db: Session = Depends(get_db),
    _rl: None = Depends(rate_limit("contact:submit", max_requests=5, window_seconds=300)),
) -> ContactResponse:
    """Submit a contact form enquiry.

    The enquiry is forwarded to the business owner's support email and a
    lightweight record is kept in the database for reference.
    """
    # Store a lightweight record for tracking (not a full user account)
    entry = models.ContactEntry(
        name=body.name,
        email=body.email,
        phone=body.phone,
        message=body.message,
    )
    db.add(entry)
    db.commit()

    # Forward to the business owner
    subject, email_body = _build_contact_email(body)
    try:
        send_email(settings.nite_dsp_support_email, subject, email_body)
        logger.info("contact_submit email_forwarded id=%s", entry.id)
    except Exception:
        # Don't fail the request if email forwarding fails -- the record is
        # still saved and the user gets a success response.
        # Log the row id, never the raw email address (PII).
        logger.exception("contact_submit email_forward_failed id=%s", entry.id)

    return ContactResponse(
        ok=True,
        message="Thanks for your enquiry. We'll get back to you within 24 hours.",
    )
