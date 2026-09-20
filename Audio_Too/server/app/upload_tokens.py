"""Signed upload links for client stem delivery (per project)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 14  # 14 days


def signing_secret() -> bytes:
    key = (
        os.getenv("AUDIO_TOO_UPLOAD_SIGNING_KEY", "").strip()
        or os.getenv("AUDIO_TOO_INVOICE_SIGNING_KEY", "").strip()
        or os.getenv("AUDIO_TOO_DASHBOARD_PASSWORD", "").strip()
        or "audio-too-admin"
    )
    return key.encode("utf-8")


def make_upload_token(project_id: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    expires = int(time.time()) + ttl_seconds
    payload = f"{project_id}:{expires}"
    digest = hmac.new(signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{project_id}.{expires}.{digest}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def verify_upload_token(project_id: str, token: str) -> bool:
    if not token or not project_id:
        return False
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        parts = decoded.split(".")
        if len(parts) != 3:
            return False
        token_id, expires_text, digest = parts
        if token_id != project_id:
            return False
        if int(expires_text) < int(time.time()):
            return False
        payload = f"{project_id}:{expires_text}"
        expected = hmac.new(signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, digest)
    except (ValueError, OSError):
        return False


def project_id_from_token(token: str) -> str | None:
    if not token:
        return None
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        parts = decoded.split(".")
        if len(parts) != 3:
            return None
        project_id, expires_text, digest = parts
        if int(expires_text) < int(time.time()):
            return None
        payload = f"{project_id}:{expires_text}"
        expected = hmac.new(signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, digest):
            return None
        return project_id
    except (ValueError, OSError):
        return None


def upload_url(project_id: str, *, host: str = "127.0.0.1", port: int = 8080, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict:
    token = make_upload_token(project_id, ttl_seconds=ttl_seconds)
    query = urlencode({"token": token})
    return {
        "project_id": project_id,
        "upload_url": f"http://{host}:{port}/upload?{query}",
        "token": token,
        "expires_in_days": ttl_seconds // 86400,
    }
