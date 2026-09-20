"""SMTP adapter policy and provider-receipt tests."""

from __future__ import annotations

import pytest

from app import email_notify


def test_send_email_requires_explicit_external_action_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUDIO_TOO_ALLOW_EXTERNAL_EMAIL", raising=False)
    monkeypatch.setenv("AUDIO_TOO_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("AUDIO_TOO_EMAIL_FROM", "studio@example.com")
    with pytest.raises(email_notify.EmailDeliveryDisabled):
        email_notify.send_email(
            to="artist@example.com", subject="Mix", text_body="Ready"
        )


def test_send_email_returns_message_id_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_ALLOW_EXTERNAL_EMAIL", "1")
    monkeypatch.setenv("AUDIO_TOO_EMAIL_ENABLED", "1")
    monkeypatch.setenv("AUDIO_TOO_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("AUDIO_TOO_SMTP_PORT", "587")
    monkeypatch.setenv("AUDIO_TOO_EMAIL_FROM", "studio@example.com")
    monkeypatch.delenv("AUDIO_TOO_SMTP_USER", raising=False)
    monkeypatch.delenv("AUDIO_TOO_SMTP_PASSWORD", raising=False)
    sent = []

    class SMTP:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            assert (host, port, timeout) == ("smtp.example.com", 587, 30)

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def ehlo(self) -> None:
            pass

        def starttls(self, context) -> None:
            assert context == "tls-context"

        def login(self, _user: str, _password: str) -> None:
            raise AssertionError("No credentials were configured")

        def send_message(self, message):
            sent.append(message)
            return {}

    monkeypatch.setattr(email_notify.smtplib, "SMTP", SMTP)
    monkeypatch.setattr(
        email_notify.ssl, "create_default_context", lambda: "tls-context"
    )

    receipt = email_notify.send_email(
        to="artist@example.com", subject="Your mix", text_body="Ready"
    )

    assert receipt.startswith("<") and receipt.endswith(">")
    assert sent[0]["To"] == "artist@example.com"
    assert sent[0]["Message-ID"] == receipt
