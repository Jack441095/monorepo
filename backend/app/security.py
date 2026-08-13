"""Token generation/hashing and signed session cookies.

Magic-link tokens are stored hashed (sha256), never in plaintext, following
the same "don't store the secret itself" principle as a password hash --
see docs/NITE_DSP_ACCOUNT_ARCHITECTURE.md. Session cookies are itsdangerous
signed tokens (not JWT -- no need for third-party verification, this is a
single first-party backend), keyed off Settings.session_secret.
"""
from __future__ import annotations

import hashlib
import secrets

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import settings

SESSION_COOKIE_NAME = "nitedsp_session"
SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60  # 30 days

_serializer = URLSafeTimedSerializer(settings.session_secret, salt="nitedsp-session")
_download_serializer = URLSafeTimedSerializer(settings.session_secret, salt="nitedsp-download")
DOWNLOAD_URL_MAX_AGE_SECONDS = 15 * 60


def generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_session_cookie(user_id: str) -> str:
    return _serializer.dumps({"user_id": user_id})


def read_session_cookie(cookie_value: str) -> str | None:
    """Returns the user_id if the cookie is valid and unexpired, else None."""
    try:
        data = _serializer.loads(cookie_value, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id")


def create_download_token(release_id: str, user_id: str) -> str:
    return _download_serializer.dumps({"release_id": release_id, "user_id": user_id})


def read_download_token(token: str) -> dict | None:
    """Returns {release_id, user_id} if the token is valid and unexpired, else None."""
    try:
        return _download_serializer.loads(token, max_age=DOWNLOAD_URL_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
