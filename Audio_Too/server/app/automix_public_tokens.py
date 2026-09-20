"""Signed, time-limited tokens for public self-serve AutoMix job status.

Mirrors stem_separation_tokens.py / mix_report_tokens.py: an HMAC-SHA256
token scopes read access to a single job id for a bounded time, so a
public self-serve caller (e.g. the KENN app's unified upload widget) can
poll status without a dashboard session.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

DEFAULT_TTL_SECONDS = 60 * 60 * 24  # 24 hours -- long enough to poll and check results


def signing_secret() -> bytes:
    key = (
        os.getenv("AUDIO_TOO_AUTOMIX_PUBLIC_SIGNING_KEY", "").strip()
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
