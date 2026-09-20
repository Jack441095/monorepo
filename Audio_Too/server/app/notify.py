"""Optional local and email notifications for website events."""

from __future__ import annotations

import os
import subprocess
import sys

from action_policy import action_allowed
from delivery_service import queue_enquiry_notification
from email_notify import email_enabled, smtp_settings


def notifications_enabled() -> bool:
    return os.getenv("AUDIO_TOO_NOTIFY", "1").strip().lower() not in {"0", "false", "no", "off"}


def notify_new_enquiry(
    name: str,
    service: str,
    *,
    email: str = "",
    message: str = "",
    deadline: str = "",
    client_id: str = "",
) -> None:
    if notifications_enabled():
        _desktop_notification(name, service)
    if email_enabled() and client_id:
        queue_enquiry_notification(
            enquiry_id=client_id,
            destination=smtp_settings()["to"],
            name=name,
            email=email,
            service=service,
            message=message,
            deadline=deadline,
        )


def _desktop_notification(name: str, service: str) -> None:
    title = "Audio_Too — new enquiry"
    body = f"{name} · {service}"
    if sys.platform == "darwin" and action_allowed("desktop_automation"):
        script = (
            f'display notification "{_escape_apple(body)}" '
            f'with title "{_escape_apple(title)}" sound name "Glass"'
        )
        subprocess.run(["osascript", "-e", script], check=False)
        return
    if action_allowed("desktop_automation"):
        print(f"[notify] {title}: {body}", flush=True)


def _escape_apple(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')
