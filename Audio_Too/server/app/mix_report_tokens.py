"""Signed, time-limited tokens for shareable Mix Doctor report links.

Mirrors `invoice_tokens.py`: an HMAC-SHA256 token scopes read access to a
single review id for a bounded time, so a prospect can open one report without
a dashboard session and without a password in the URL. The report route
(`/mix-report/<id>`) is classified SIGNED_TOKEN in `audio_too.endpoint_policy`,
so it bypasses the dashboard auth gate and self-verifies the token here.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from urllib.parse import quote, urlencode


DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days — a shared report link is longer-lived than an invoice


def signing_secret() -> bytes:
    key = (
        os.getenv("AUDIO_TOO_MIX_REPORT_SIGNING_KEY", "").strip()
        or os.getenv("AUDIO_TOO_INVOICE_SIGNING_KEY", "").strip()
        or os.getenv("AUDIO_TOO_DASHBOARD_PASSWORD", "").strip()
        or "audio-too-admin"
    )
    return key.encode("utf-8")


def make_report_token(review_id: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    expires = int(time.time()) + ttl_seconds
    payload = f"{review_id}:{expires}"
    digest = hmac.new(signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{review_id}.{expires}.{digest}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def verify_report_token(review_id: str, token: str) -> bool:
    if not token:
        return False
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        parts = decoded.split(".")
        if len(parts) != 3:
            return False
        token_id, expires_text, digest = parts
        if token_id != review_id:
            return False
        if int(expires_text) < int(time.time()):
            return False
        payload = f"{review_id}:{expires_text}"
        expected = hmac.new(signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, digest)
    except (ValueError, OSError):
        return False


def report_url(review_id: str, *, host: str = "127.0.0.1", port: int = 8080) -> dict:
    token = make_report_token(review_id)
    encoded = quote(review_id, safe="")
    query = urlencode({"token": token})
    return {
        "url": f"http://{host}:{port}/mix-report/{encoded}?{query}",
        "expires_in_days": DEFAULT_TTL_SECONDS // 86400,
    }
