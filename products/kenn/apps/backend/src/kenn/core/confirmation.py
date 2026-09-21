"""Signed, expiring confirmations for consequential KENN actions.

Ported into this standalone repository as KENN-owned code (not a live
dependency on the old "Thursday" hub product -- this repo's operating
rules explicitly disallow reintroducing that dependency). Pure stdlib
HMAC-signed, time-boxed token issuance/verification; no external calls,
no coupling to anything Thursday-specific.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from threading import Lock

DEFAULT_TTL_SECONDS = 300
MAX_TTL_SECONDS = 3600
MAX_USED_TOKENS = 10_000
_PROCESS_SECRET = secrets.token_bytes(32)
_USED_TOKENS: set[str] = set()
_TOKEN_LOCK = Lock()


def _secret() -> bytes:
    """Return a process-bound signing key.

    A configured root secret may make tokens reproducible across deployments,
    but it must not make a pending mutation valid after this companion
    restarts. Deriving the signing key with the per-process secret gives us
    both properties: configuration controls the root, while every restart
    invalidates all outstanding confirmations and in-memory proposals.
    """
    configured = os.environ.get("KENN_CONFIRMATION_SECRET", "").encode("utf-8")
    root = configured or b"kenn-confirmation-default-root"
    return hmac.new(root, _PROCESS_SECRET, hashlib.sha256).digest()


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
    expires_at = int(time.time()) + min(MAX_TTL_SECONDS, max(1, int(ttl_seconds)))
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
    if version != "v1" or (now if now is not None else int(time.time())) >= expires_at:
        return False
    expected = _signature(session_id, service_id, text, expires_at, nonce)
    return hmac.compare_digest(supplied, expected)


def consume_confirmation(
    token: str, *, session_id: str, service_id: str, text: str, now: int | None = None
) -> bool:
    """Verify and consume a token exactly once.

    Verification remains side-effect free for UI previews.  Mutation paths
    must use this function so a retry cannot replay the same confirmed write.
    """
    if not verify_confirmation(token, session_id=session_id, service_id=service_id, text=text, now=now):
        return False
    with _TOKEN_LOCK:
        now_value = now if now is not None else int(time.time())
        expired = set()
        for used in _USED_TOKENS:
            try:
                if int(used.split(".")[1], 16) <= now_value:
                    expired.add(used)
            except (IndexError, ValueError):
                expired.add(used)
        _USED_TOKENS.difference_update(expired)
        if token in _USED_TOKENS:
            return False
        # Never evict a still-live consumed token: that would make replay
        # possible. Saturation therefore fails closed until tokens expire.
        if len(_USED_TOKENS) >= MAX_USED_TOKENS:
            return False
        _USED_TOKENS.add(token)
    return True
