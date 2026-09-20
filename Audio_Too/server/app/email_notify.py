"""Optional SMTP email when a website enquiry is received."""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid

from action_policy import action_allowed


class EmailDeliveryDisabled(RuntimeError):
    pass


class EmailDeliveryError(RuntimeError):
    pass


def smtp_delivery_enabled() -> bool:
    if not action_allowed("external_email"):
        return False
    if os.getenv("AUDIO_TOO_EMAIL_ENABLED", "").strip().lower() in {"0", "false", "no", "off"}:
        return False
    settings = smtp_settings()
    return bool(settings.get("host") and settings.get("from_addr"))


def email_enabled() -> bool:
    return smtp_delivery_enabled() and bool(smtp_settings().get("to"))


def smtp_settings() -> dict:
    return {
        "host": os.getenv("AUDIO_TOO_SMTP_HOST", "").strip(),
        "port": int(os.getenv("AUDIO_TOO_SMTP_PORT", "587")),
        "user": os.getenv("AUDIO_TOO_SMTP_USER", "").strip(),
        "password": os.getenv("AUDIO_TOO_SMTP_PASSWORD", "").strip(),
        "from_addr": os.getenv("AUDIO_TOO_EMAIL_FROM", os.getenv("AUDIO_TOO_SMTP_USER", "")).strip(),
        "to": os.getenv("AUDIO_TOO_EMAIL_TO", os.getenv("AUDIO_TOO_SMTP_USER", "")).strip(),
    }


def send_enquiry_email(
    *,
    name: str,
    email: str,
    service: str,
    message: str,
    deadline: str = "",
    client_id: str = "",
) -> bool:
    if not email_enabled():
        return False

    settings = smtp_settings()
    subject = f"Audio_Too enquiry — {name} ({service})"
    body_lines = [
        "New project enquiry from the Audio_Too website.",
        "",
        f"Name: {name}",
        f"Email: {email}",
        f"Service: {service}",
        f"Deadline: {deadline or '(not specified)'}",
    ]
    if client_id:
        body_lines.append(f"Client record: {client_id}")
    body_lines.extend(["", "Message:", message, "", "Open the dashboard: http://127.0.0.1:8080/dashboard"])
    body = "\n".join(body_lines)

    try:
        send_email(to=settings["to"], subject=subject, text_body=body)
        return True
    except (EmailDeliveryDisabled, EmailDeliveryError) as exc:
        if os.getenv("AUDIO_TOO_EMAIL_DEBUG", "").strip() in {"1", "true", "yes"}:
            print(f"[email] failed: {exc}", flush=True)
        return False


def send_email(*, to: str, subject: str, text_body: str) -> str:
    """Send one reviewed message and return its provider-facing Message-ID receipt."""
    if not smtp_delivery_enabled():
        raise EmailDeliveryDisabled(
            "External email is disabled or SMTP delivery is not configured."
        )
    settings = smtp_settings()
    msg = EmailMessage()
    msg["Message-ID"] = make_msgid()
    msg["Subject"] = subject
    msg["From"] = settings["from_addr"]
    msg["To"] = to
    msg.set_content(text_body)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(settings["host"], settings["port"], timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            if settings["user"] and settings["password"]:
                server.login(settings["user"], settings["password"])
            refused = server.send_message(msg)
        if refused:
            raise EmailDeliveryError("SMTP refused one or more recipients.")
    except (OSError, ValueError) as exc:
        raise EmailDeliveryError("SMTP delivery failed after delivery began.") from exc
    return str(msg["Message-ID"])
