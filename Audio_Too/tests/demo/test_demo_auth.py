"""Tests for password-protected demo sessions."""

from __future__ import annotations

import pytest

import demo_auth


def test_demo_unconfigured_rejects_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUDIO_TOO_DEMO_PASSWORD", raising=False)
    assert not demo_auth.demo_configured()
    assert not demo_auth.verify_password("anything")


def test_demo_password_and_session_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_DEMO_PASSWORD", "tester-secret")
    monkeypatch.setenv("AUDIO_TOO_DEMO_SESSION_SECRET", "demo-session-secret")
    assert demo_auth.demo_configured()
    assert demo_auth.verify_password("tester-secret")
    assert not demo_auth.verify_password("wrong")
    token = demo_auth.make_demo_token(ttl_seconds=3600)
    assert demo_auth.verify_demo_token(token)
    assert demo_auth.demo_session_id(token)


def test_expired_demo_session_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_DEMO_SESSION_SECRET", "demo-session-secret")
    token = demo_auth.make_demo_token(ttl_seconds=-5)
    assert not demo_auth.verify_demo_token(token)
