"""Signed, time-limited tokens for invoice HTML/PDF links (no password in URL)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from urllib.parse import quote, urlencode


DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


def signing_secret() -> bytes:
    key = (
        os.getenv("AUDIO_TOO_INVOICE_SIGNING_KEY", "").strip()
        or os.getenv("AUDIO_TOO_DASHBOARD_PASSWORD", "").strip()
        or "audio-too-admin"
    )
    return key.encode("utf-8")


def make_invoice_token(invoice_id: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    expires = int(time.time()) + ttl_seconds
    payload = f"{invoice_id}:{expires}"
    digest = hmac.new(signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{invoice_id}.{expires}.{digest}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def verify_invoice_token(invoice_id: str, token: str) -> bool:
    if not token:
        return False
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        parts = decoded.split(".")
        if len(parts) != 3:
            return False
        token_id, expires_text, digest = parts
        if token_id != invoice_id:
            return False
        if int(expires_text) < int(time.time()):
            return False
        payload = f"{invoice_id}:{expires_text}"
        expected = hmac.new(signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, digest)
    except (ValueError, OSError):
        return False


def invoice_urls(invoice_id: str, *, host: str = "127.0.0.1", port: int = 8080) -> dict:
    token = make_invoice_token(invoice_id)
    base = f"http://{host}:{port}"
    encoded = quote(invoice_id, safe="")
    query = urlencode({"token": token})
    return {
        "html_url": f"{base}/invoice/{encoded}?{query}",
        "pdf_url": f"{base}/invoice/{encoded}.pdf?{query}",
        "expires_in_days": DEFAULT_TTL_SECONDS // 86400,
    }
