"""Signed, expiring confirmations for consequential actions."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

DEFAULT_TTL_SECONDS = 300
_PROCESS_SECRET = secrets.token_bytes(32)


def _secret() -> bytes:
    configured = os.environ.get("THURSDAY_CONFIRMATION_SECRET", "").encode("utf-8")
    return configured or _PROCESS_SECRET


def _request_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def _signature(session_id: str, service_id: str, text: str, expires_at: int, nonce: str) -> str:
    message = "|".join(
        (session_id, service_id, _request_hash(text), str(expires_at), nonce)
    ).encode("utf-8")
    return hmac.new(_secret(), message, hashlib.sha256).hexdigest()[:32]


def issue_confirmation(
    *, session_id: str, service_id: str, text: str, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> tuple[str, dict]:
    """Issue a compact token and the server-side pending-action record."""
    expires_at = int(time.time()) + max(1, int(ttl_seconds))
    nonce = secrets.token_hex(4)
    signature = _signature(session_id, service_id, text, expires_at, nonce)
    token = f"v1.{expires_at:x}.{nonce}.{signature}"
    return token, {
        "service_id": service_id,
        "text": text,
        "expires_at": expires_at,
        "nonce": nonce,
        "token": token,
    }


def verify_confirmation(
    token: str, *, session_id: str, service_id: str, text: str, now: int | None = None
) -> bool:
    """Verify signature, expiry, session, service, and request binding."""
    try:
        version, expiry_hex, nonce, supplied = token.split(".")
        expires_at = int(expiry_hex, 16)
    except (TypeError, ValueError):
        return False
    if version != "v1" or (now if now is not None else int(time.time())) > expires_at:
        return False
    expected = _signature(session_id, service_id, text, expires_at, nonce)
    return hmac.compare_digest(supplied, expected)
