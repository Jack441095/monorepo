#!/usr/bin/env python3
"""Send a test enquiry email using .env SMTP settings."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

from email_notify import email_enabled, send_enquiry_email  # noqa: E402


def main() -> int:
    if not email_enabled():
        print("Email not configured. Set AUDIO_TOO_SMTP_HOST and AUDIO_TOO_EMAIL_TO in .env")
        return 1
    ok = send_enquiry_email(
        name="Test Client",
        email="test@example.com",
        service="Mixing",
        message="This is a test enquiry email from scripts/test_email_config.py.",
        deadline="N/A",
        client_id="test",
    )
    if ok:
        print("Test email sent.")
        return 0
    print("Send failed. Set AUDIO_TOO_EMAIL_DEBUG=1 and try again.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
