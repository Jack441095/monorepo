"""Outbound email -- see Section 63/64 and config.py's email_provider comment.

"console" logs the email for local/staging use.
"resend" delivers via the Resend API (https://resend.com).
Any other value raises rather than silently pretending to send.
"""
from __future__ import annotations

import logging

import httpx

from .config import settings

logger = logging.getLogger("nitedsp.email")


def send_email(to: str, subject: str, body: str) -> None:
    if settings.email_provider == "console":
        logger.info("EMAIL to=%s from=%s subject=%r\n%s", to, settings.email_from_address, subject, body)
        return
    elif settings.email_provider == "resend":
        if not settings.resend_api_key:
            raise ValueError("resend_api_key is empty")

        html_body = body.replace("\n", "<br/>")

        headers = {
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "from": f"{settings.email_from_name} <{settings.email_from_address}>",
            "to": [to],
            "subject": subject,
            "html": html_body,
            "text": body,
        }

        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                json=payload,
                headers=headers,
                timeout=10.0,
            )
            response.raise_for_status()
            logger.info("Email sent to %s via Resend", to)
        except Exception as e:
            logger.error("Failed to send email to %s via Resend: %s", to, e)
            raise RuntimeError(f"Email delivery failed: {e}") from e
        return
    raise NotImplementedError(
        f"email_provider={settings.email_provider!r} is not implemented"
    )
