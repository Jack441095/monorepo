"""Outbound email -- see Section 63/64 and config.py's email_provider comment.

"console" is the only provider implemented right now (correct for local
staging, where no transactional email account exists yet -- see
docs/HUMAN_COMMERCIAL_REQUIREMENTS.md). Any other value raises rather than
silently pretending to send, so a misconfigured deployment fails loudly
instead of losing real emails.
"""
from __future__ import annotations

import logging

from .config import settings

logger = logging.getLogger("nitedsp.email")


def send_email(to: str, subject: str, body: str) -> None:
    if settings.email_provider == "console":
        logger.info("EMAIL to=%s from=%s subject=%r\n%s", to, settings.email_from_address, subject, body)
        return
    raise NotImplementedError(
        f"email_provider={settings.email_provider!r} is not implemented -- "
        "only 'console' exists until a real transactional email account is configured"
    )
