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
import re
import secrets
import time
from threading import Lock

DEFAULT_TTL_SECONDS = 300
MAX_TTL_SECONDS = 3600
MAX_USED_TOKENS = 10_000
MAX_ISSUED_TOKENS = 10_000
_PROCESS_SECRET = secrets.token_bytes(32)
_USED_TOKENS: set[str] = set()
_ISSUED_TOKENS: dict[str, tuple[str, int]] = {}
_REVOKED_TOKENS: set[str] = set()
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


# Browser clients echo proposals through JSON.stringify, which drops a float's
# trailing ".0" and formats small magnitudes differently from Python, so equal
# numbers must hash equally. Word-adjacent digits (hex hashes, names) are left alone.
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?(?![\w.])")


def _canonical_number(match: re.Match[str]) -> str:
    value = float(match.group(0))
    return "0.0" if value == 0 else repr(value)


def _request_hash(text: str) -> str:
    canonical = _NUMBER.sub(_canonical_number, text.strip())
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _signature(session_id: str, service_id: str, text: str, expires_at: int, nonce: str) -> str:
    message = "|".join(
        (session_id, service_id, _request_hash(text), str(expires_at), nonce)
    ).encode("utf-8")
    return hmac.new(_secret(), message, hashlib.sha256).hexdigest()[:32]


def _prune_tokens(now: int) -> None:
    # Keep revoked signatures until expiry: dropping a live tombstone would let
    # a browser apply its held proposal again. Callers hold _TOKEN_LOCK.
    expired = [token for token, (_, expiry) in _ISSUED_TOKENS.items() if expiry <= now]
    for token in expired:
        del _ISSUED_TOKENS[token]
        _REVOKED_TOKENS.discard(token)
    expired_used = set()
    for token in _USED_TOKENS:
        try:
            if int(token.split(".")[1], 16) <= now:
                expired_used.add(token)
        except (IndexError, ValueError):
            expired_used.add(token)
    _USED_TOKENS.difference_update(expired_used)


def issue_confirmation(
    *, session_id: str, service_id: str, text: str, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> tuple[str, dict]:
    """Issue a compact token and the server-side pending-action record."""
    with _TOKEN_LOCK:
        now = int(time.time())
        _prune_tokens(now)
        if len(_ISSUED_TOKENS) >= MAX_ISSUED_TOKENS:
            raise ValueError("Too many pending confirmations; wait for an earlier confirmation to expire.")
        expires_at = now + min(MAX_TTL_SECONDS, max(1, int(ttl_seconds)))
        nonce = secrets.token_hex(4)
        signature = _signature(session_id, service_id, text, expires_at, nonce)
        token = f"v1.{expires_at:x}.{nonce}.{signature}"
        _ISSUED_TOKENS[token] = (session_id, expires_at)
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
    """Verify signature, expiry, revocation, session, service, and request binding."""
    if not isinstance(token, str):
        return False
    try:
        version, expiry_hex, nonce, supplied = token.split(".")
        expires_at = int(expiry_hex, 16)
    except (TypeError, ValueError):
        return False
    if version != "v1" or (now if now is not None else int(time.time())) >= expires_at:
        return False
    expected = _signature(session_id, service_id, text, expires_at, nonce)
    if not hmac.compare_digest(supplied, expected):
        return False
    with _TOKEN_LOCK:
        return token not in _REVOKED_TOKENS


def revoke_confirmation(token: str, *, session_id: str, now: int | None = None) -> bool:
    """Dismiss an unconsumed token owned by this exact chat.

    A false result cannot promise cancellation: the token may have expired,
    been dismissed, or already been consumed by an action in progress.
    """
    if not isinstance(token, str) or not isinstance(session_id, str) or not session_id.strip():
        return False
    with _TOKEN_LOCK:
        _prune_tokens(now if now is not None else int(time.time()))
        issued = _ISSUED_TOKENS.get(token)
        if issued is None or issued[0] != session_id or token in _USED_TOKENS or token in _REVOKED_TOKENS:
            return False
        _REVOKED_TOKENS.add(token)
        return True


def revoke_session_confirmations(*, session_id: str, now: int | None = None) -> int:
    """Revoke this chat's pending confirmations across all action services."""
    if not isinstance(session_id, str) or not session_id.strip():
        return 0
    with _TOKEN_LOCK:
        _prune_tokens(now if now is not None else int(time.time()))
        tokens = {
            token for token, (owner, _) in _ISSUED_TOKENS.items()
            if owner == session_id and token not in _USED_TOKENS and token not in _REVOKED_TOKENS
        }
        _REVOKED_TOKENS.update(tokens)
        return len(tokens)


def pending_confirmation_count(*, session_id: str, now: int | None = None) -> int:
    """Observe unconsumed confirmations owned by this exact chat."""
    if not isinstance(session_id, str) or not session_id.strip():
        return 0
    with _TOKEN_LOCK:
        _prune_tokens(now if now is not None else int(time.time()))
        return sum(
            owner == session_id and token not in _USED_TOKENS and token not in _REVOKED_TOKENS
            for token, (owner, _) in _ISSUED_TOKENS.items()
        )


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
        _prune_tokens(now_value)
        # Dismiss and Apply share this lock. Recheck after preview verification
        # so a revoke or expiry between verification and consumption wins.
        if token in _USED_TOKENS or token in _REVOKED_TOKENS or int(token.split(".")[1], 16) <= now_value:
            return False
        # Never evict a still-live consumed token: that would make replay
        # possible. Saturation therefore fails closed until tokens expire.
        if len(_USED_TOKENS) >= MAX_USED_TOKENS:
            return False
        _USED_TOKENS.add(token)
        _ISSUED_TOKENS.pop(token, None)
    return True
