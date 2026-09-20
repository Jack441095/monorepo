"""Tests for signed invoice links."""

from __future__ import annotations

import pytest

import invoice_tokens


def test_round_trip_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_INVOICE_SIGNING_KEY", "test-signing-key-only")
    token = invoice_tokens.make_invoice_token("inv-42", ttl_seconds=3600)
    assert invoice_tokens.verify_invoice_token("inv-42", token)
    assert not invoice_tokens.verify_invoice_token("inv-99", token)


def test_expired_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_INVOICE_SIGNING_KEY", "test-signing-key-only")
    token = invoice_tokens.make_invoice_token("inv-1", ttl_seconds=-10)
    assert not invoice_tokens.verify_invoice_token("inv-1", token)


def test_invoice_urls_include_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_INVOICE_SIGNING_KEY", "test-signing-key-only")
    urls = invoice_tokens.invoice_urls("ABC-1", host="127.0.0.1", port=8080)
    assert "token=" in urls["html_url"]
    assert urls["pdf_url"].endswith(".pdf?token=") or "token=" in urls["pdf_url"]
