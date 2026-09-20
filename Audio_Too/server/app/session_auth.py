"""Signed HttpOnly session cookies for the local dashboard."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time

SESSION_COOKIE = "audio_too_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
_revoked_sessions: dict[str, int] = {}


def development_mode() -> bool:
    return os.getenv("AUDIO_TOO_DEV", "").strip().lower() in {"1", "true", "yes", "on"}


def session_secret() -> bytes:
    key = os.getenv("AUDIO_TOO_SESSION_SECRET", "").strip()
    if not key and development_mode():
        key = os.getenv("AUDIO_TOO_DASHBOARD_PASSWORD", "").strip() or "audio-too-local-dev"
    if not key:
        raise RuntimeError("AUDIO_TOO_SESSION_SECRET is required outside development mode.")
    return key.encode("utf-8")


def dashboard_password() -> str:
    return os.getenv("AUDIO_TOO_DASHBOARD_PASSWORD", "audio-too-admin").strip() or "audio-too-admin"


def verify_password(password: str) -> bool:
    expected = dashboard_password()
    if not password or not expected:
        return False
    return secrets.compare_digest(password.encode("utf-8"), expected.encode("utf-8"))


def make_session_token(*, ttl_seconds: int = SESSION_TTL_SECONDS) -> str:
    issued = int(time.time())
    expires = int(time.time()) + ttl_seconds
    session_id = secrets.token_urlsafe(18)
    payload = f"dashboard:v2:{issued}:{expires}:{session_id}"
    digest = hmac.new(session_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"v2.{issued}.{expires}.{session_id}.{digest}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def make_csrf_token(session_token: str) -> str:
    """Return a session-bound token safe to expose to same-origin JavaScript."""
    if not verify_session_token(session_token):
        return ""
    return hmac.new(
        session_secret(),
        f"csrf:{session_token}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_csrf_token(session_token: str, csrf_token: str) -> bool:
    expected = make_csrf_token(session_token)
    return bool(expected and csrf_token and hmac.compare_digest(expected, csrf_token))


def verify_session_token(token: str) -> bool:
    if not token:
        return False
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        parts = decoded.split(".", 4)
        if len(parts) != 5 or parts[0] != "v2":
            return False
        _, issued_text, expires_text, session_id, digest = parts
        issued = int(issued_text)
        expires = int(expires_text)
        now = int(time.time())
        if issued > now + 60 or expires < now or expires <= issued:
            return False
        _purge_revocations(now)
        if session_id in _revoked_sessions:
            return False
        payload = f"dashboard:v2:{issued_text}:{expires_text}:{session_id}"
        expected = hmac.new(session_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, digest)
    except (ValueError, OSError):
        return False


def revoke_session_token(token: str) -> bool:
    """Revoke one valid session token until its natural expiry."""
    if not verify_session_token(token):
        return False
    padded = token + "=" * (-len(token) % 4)
    decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    _, _, expires_text, session_id, _ = decoded.split(".", 4)
    _revoked_sessions[session_id] = int(expires_text)
    return True


def _purge_revocations(now: int | None = None) -> None:
    current = int(time.time()) if now is None else now
    expired = [session_id for session_id, expires in _revoked_sessions.items() if expires < current]
    for session_id in expired:
        _revoked_sessions.pop(session_id, None)


def cookie_value(header: str | None, name: str = SESSION_COOKIE) -> str:
    if not header:
        return ""
    for part in header.split(";"):
        piece = part.strip()
        if piece.startswith(f"{name}="):
            return piece.split("=", 1)[1].strip()
    return ""


def session_cookie_header(
    *,
    ttl_seconds: int = SESSION_TTL_SECONDS,
    clear: bool = False,
    token: str = "",
    secure: bool | None = None,
) -> str:
    if secure is None:
        secure = os.getenv("AUDIO_TOO_COOKIE_SECURE", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    secure_flag = "; Secure" if secure else ""
    if clear:
        return f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict{secure_flag}; Max-Age=0"
    token = token or make_session_token(ttl_seconds=ttl_seconds)
    return (
        f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict"
        f"{secure_flag}; Max-Age={ttl_seconds}"
    )
