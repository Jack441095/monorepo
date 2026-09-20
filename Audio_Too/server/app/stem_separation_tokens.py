"""Signed, time-limited tokens for stem-separation job status/download links.

Mirrors mix_report_tokens.py: an HMAC-SHA256 token scopes read access to a
single job id for a bounded time, so the uploader can poll status and
download their own stems without a dashboard session. The status/download
routes are PUBLIC in audio_too.endpoint_policy (query-param based, like
/api/automix/status?id=), and self-verify the token here rather than
needing a new SIGNED_TOKEN path-prefix entry.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

DEFAULT_TTL_SECONDS = 60 * 60 * 24  # 24 hours -- long enough to poll and download, not a share link


def signing_secret() -> bytes:
    key = (
        os.getenv("AUDIO_TOO_STEM_SEPARATION_SIGNING_KEY", "").strip()
        or os.getenv("AUDIO_TOO_MIX_REPORT_SIGNING_KEY", "").strip()
        or os.getenv("AUDIO_TOO_DASHBOARD_PASSWORD", "").strip()
        or "audio-too-admin"
    )
    return key.encode("utf-8")


def make_job_token(job_id: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    expires = int(time.time()) + ttl_seconds
    payload = f"{job_id}:{expires}"
    digest = hmac.new(signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{job_id}.{expires}.{digest}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def verify_job_token(job_id: str, token: str) -> bool:
    if not token:
        return False
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        parts = decoded.split(".")
        if len(parts) != 3:
            return False
        token_id, expires_text, digest = parts
        if token_id != job_id:
            return False
        if int(expires_text) < int(time.time()):
            return False
        payload = f"{job_id}:{expires_text}"
        expected = hmac.new(signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, digest)
    except (ValueError, OSError):
        return False
