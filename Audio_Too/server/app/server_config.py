"""Validated configuration for the local Website process."""

from __future__ import annotations

import os

HOST = os.getenv("AUDIO_TOO_HOST", "127.0.0.1").strip() or "127.0.0.1"
PORT = int(os.getenv("AUDIO_TOO_PORT", "8080"))
DEFAULT_PASSWORD = "audio-too-admin"


# Env vars whose signing_secret()/demo_secret() helpers silently fall back to
# AUDIO_TOO_DASHBOARD_PASSWORD when unset -- see docs/codebase_scan_12_07.md
# §4.1 "signing key reused across trust boundaries". Warned about (not a hard
# fail) since these links are used far less often than the dashboard itself
# and a surprise startup refusal would be worse than a visible warning.
_SIGNING_KEY_ENV_VARS = (
    "AUDIO_TOO_UPLOAD_SIGNING_KEY",
    "AUDIO_TOO_INVOICE_SIGNING_KEY",
    "AUDIO_TOO_DEMO_SESSION_SECRET",
)


def validate_startup_secrets() -> None:
    dashboard_password = os.getenv("AUDIO_TOO_DASHBOARD_PASSWORD", DEFAULT_PASSWORD)
    if os.getenv("AUDIO_TOO_DEV", "").strip().lower() in {"1", "true", "yes", "on"}:
        if dashboard_password == DEFAULT_PASSWORD:
            print("Warning: using default dashboard password (AUDIO_TOO_DEV is set).")
        return
    if not dashboard_password or dashboard_password == DEFAULT_PASSWORD:
        print(
            "Set AUDIO_TOO_DASHBOARD_PASSWORD in .env before starting the server.\n"
            "For local dev only, set AUDIO_TOO_DEV=1 in .env."
        )
        raise SystemExit(1)
    session_secret = os.getenv("AUDIO_TOO_SESSION_SECRET", "").strip()
    if len(session_secret) < 32:
        print("Set AUDIO_TOO_SESSION_SECRET to a dedicated random value of at least 32 characters.")
        raise SystemExit(1)
    unset_signing_keys = [name for name in _SIGNING_KEY_ENV_VARS if not os.getenv(name, "").strip()]
    if unset_signing_keys:
        print(
            "Warning: "
            + ", ".join(unset_signing_keys)
            + " not set -- those links currently fall back to signing with "
            "AUDIO_TOO_DASHBOARD_PASSWORD. Set dedicated random values in .env "
            "so rotating the dashboard password doesn't also invalidate/expose them."
        )
