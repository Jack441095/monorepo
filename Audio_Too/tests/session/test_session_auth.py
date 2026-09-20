"""Tests for dashboard session cookies."""

from __future__ import annotations

import pytest

import session_auth


def test_password_and_session_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_DASHBOARD_PASSWORD", "test-dashboard-secret")
    monkeypatch.setenv("AUDIO_TOO_SESSION_SECRET", "test-session-secret-that-is-long-enough")
    assert session_auth.verify_password("test-dashboard-secret")
    assert not session_auth.verify_password("wrong")
    token = session_auth.make_session_token(ttl_seconds=3600)
    assert session_auth.verify_session_token(token)
    csrf_token = session_auth.make_csrf_token(token)
    assert session_auth.verify_csrf_token(token, csrf_token)
    assert not session_auth.verify_csrf_token(token, f"{csrf_token}tampered")


def test_session_can_be_revoked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_SESSION_SECRET", "revocation-session-secret")
    token = session_auth.make_session_token(ttl_seconds=3600)
    assert session_auth.verify_session_token(token)
    assert session_auth.revoke_session_token(token)
    assert not session_auth.verify_session_token(token)


def test_secure_cookie_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_SESSION_SECRET", "secure-cookie-session-secret")
    token = session_auth.make_session_token(ttl_seconds=60)
    assert "; Secure" not in session_auth.session_cookie_header(token=token, secure=False)
    assert "; Secure" in session_auth.session_cookie_header(token=token, secure=True)


def test_production_session_secret_has_no_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUDIO_TOO_SESSION_SECRET", raising=False)
    monkeypatch.delenv("AUDIO_TOO_DEV", raising=False)
    with pytest.raises(RuntimeError, match="AUDIO_TOO_SESSION_SECRET"):
        session_auth.make_session_token()


def test_expired_session_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_SESSION_SECRET", "session-only-secret")
    token = session_auth.make_session_token(ttl_seconds=-5)
    assert not session_auth.verify_session_token(token)
