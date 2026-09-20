"""Signed, time-limited tokens for shareable podcast-check report links.

Mirrors `mix_report_tokens.py` (same HMAC-SHA256, review-id-scoped pattern)
but the signed payload is namespaced "podcast:<id>" rather than bare
"<id>" -- a mix-report token and a podcast-report token are never
interchangeable even if a review id and a podcast report id happened to
collide, since each only verifies against its own namespaced payload.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from mix_report_tokens import signing_secret

DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days -- matches mix_report_tokens.py
_NAMESPACE = "podcast"


def make_podcast_report_token(report_id: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    expires = int(time.time()) + ttl_seconds
    payload = f"{_NAMESPACE}:{report_id}:{expires}"
    digest = hmac.new(signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{report_id}.{expires}.{digest}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def verify_podcast_report_token(report_id: str, token: str) -> bool:
    if not token:
        return False
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        parts = decoded.split(".")
        if len(parts) != 3:
            return False
        token_id, expires_text, digest = parts
        if token_id != report_id:
            return False
        if int(expires_text) < int(time.time()):
            return False
        payload = f"{_NAMESPACE}:{report_id}:{expires_text}"
        expected = hmac.new(signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, digest)
    except (ValueError, OSError):
        return False
