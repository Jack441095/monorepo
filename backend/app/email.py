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
        # Console mode is useful for local development, but email bodies can
        # contain magic links, licence keys, or other account data. Keep the
        # operational signal without writing recipient or message content to
        # logs.
        logger.info(
            "EMAIL console from_configured=%s subject_chars=%d body_bytes=%d",
            bool(settings.email_from_address),
            len(subject),
            len(body.encode("utf-8")),
        )
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
        # The From address is a verified sending domain, not a monitored
        # inbox -- replies must land on the actual support mailbox instead.
        if settings.nite_dsp_support_email and not settings.nite_dsp_support_email.endswith("@localhost.invalid"):
            payload["reply_to"] = [settings.nite_dsp_support_email]

        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                json=payload,
                headers=headers,
                timeout=10.0,
            )
            response.raise_for_status()
            logger.info("Email sent via Resend")
        except Exception as e:
            logger.error("Email delivery failed via Resend (%s)", type(e).__name__)
            raise RuntimeError(f"Email delivery failed: {e}") from e
        return
    raise NotImplementedError(
        f"email_provider={settings.email_provider!r} is not implemented"
    )
