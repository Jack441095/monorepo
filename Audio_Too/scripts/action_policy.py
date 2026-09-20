"""Explicit opt-in policy for actions that leave the local application boundary."""

from __future__ import annotations

import os

ACTION_FLAGS = {
    "external_email": "AUDIO_TOO_ALLOW_EXTERNAL_EMAIL",
    "desktop_automation": "AUDIO_TOO_ALLOW_DESKTOP_AUTOMATION",
    "daw_control": "AUDIO_TOO_ALLOW_DAW_CONTROL",
    "audio_capture": "AUDIO_TOO_ALLOW_AUDIO_CAPTURE",
}


def action_allowed(action: str) -> bool:
    variable = ACTION_FLAGS.get(action)
    if not variable:
        return False
    return os.getenv(variable, "").strip().lower() in {"1", "true", "yes", "on"}


def action_denied_message(action: str) -> str:
    variable = ACTION_FLAGS.get(action, "an explicit allow flag")
    return f"Action disabled by policy. Set {variable}=1 only after reviewing the security boundary."
