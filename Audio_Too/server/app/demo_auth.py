"""Signed tester-demo sessions for the Audio Tips LLM demo portal."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time

DEMO_COOKIE = "audio_too_demo"
DEMO_TTL_SECONDS = 60 * 60 * 24 * 3


def demo_password() -> str:
    return os.getenv("AUDIO_TOO_DEMO_PASSWORD", "").strip()


def demo_configured() -> bool:
    return bool(demo_password())


def demo_secret() -> bytes:
    key = (
        os.getenv("AUDIO_TOO_DEMO_SESSION_SECRET", "").strip()
        or os.getenv("AUDIO_TOO_SESSION_SECRET", "").strip()
        or os.getenv("AUDIO_TOO_DASHBOARD_PASSWORD", "").strip()
        or "audio-too-demo"
    )
    return key.encode("utf-8")


def verify_password(password: str) -> bool:
    expected = demo_password()
    if not password or not expected:
        return False
    return secrets.compare_digest(password.encode("utf-8"), expected.encode("utf-8"))


def make_demo_token(*, ttl_seconds: int = DEMO_TTL_SECONDS) -> str:
    expires = int(time.time()) + ttl_seconds
    session_id = secrets.token_hex(6)
    payload = f"demo:{expires}:{session_id}"
    digest = hmac.new(demo_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{expires}.{session_id}.{digest}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def demo_session_id(token: str) -> str:
    if not token:
        return ""
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        parts = decoded.split(".")
        if len(parts) == 2:
            expires_text, digest = parts
            session_id = ""
            payload = f"demo:{expires_text}"
        elif len(parts) == 3:
            expires_text, session_id, digest = parts
            payload = f"demo:{expires_text}:{session_id}"
        else:
            return ""
        if int(expires_text) < int(time.time()):
            return ""
        expected = hmac.new(demo_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, digest):
            return ""
        return session_id or "legacy"
    except (ValueError, OSError):
        return ""


def verify_demo_token(token: str) -> bool:
    return bool(demo_session_id(token))


def cookie_value(header: str | None, name: str = DEMO_COOKIE) -> str:
    if not header:
        return ""
    for part in header.split(";"):
        piece = part.strip()
        if piece.startswith(f"{name}="):
            return piece.split("=", 1)[1].strip()
    return ""


def demo_cookie_header(*, ttl_seconds: int = DEMO_TTL_SECONDS, clear: bool = False) -> str:
    if clear:
        return f"{DEMO_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
    token = make_demo_token(ttl_seconds=ttl_seconds)
    return f"{DEMO_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={ttl_seconds}"
