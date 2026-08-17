import logging

import httpx
import pytest

from app.config import settings
from app.email import send_email


def test_send_email_console(caplog):
    settings.email_provider = "console"
    settings.email_from_address = "noreply@nitedsp.co.uk"

    with caplog.at_level(logging.INFO):
        send_email("test@example.com", "Test Subject", "Test Body")

    assert "EMAIL to=test@example.com" in caplog.text
    assert "subject='Test Subject'" in caplog.text


def test_send_email_resend_missing_key():
    settings.email_provider = "resend"
    settings.resend_api_key = ""

    with pytest.raises(ValueError, match="resend_api_key is empty"):
        send_email("test@example.com", "Subject", "Body")


def test_send_email_resend_success(monkeypatch):
    settings.email_provider = "resend"
    settings.resend_api_key = "re_test_key"
    settings.email_from_name = "NITE DSP"
    settings.email_from_address = "auth@nitedsp.co.uk"

    calls = []

    def mock_post(url, json, headers, timeout):
        calls.append((url, json, headers, timeout))

        class MockResponse:
            def raise_for_status(self):
                pass

        return MockResponse()

    monkeypatch.setattr(httpx, "post", mock_post)

    send_email("test@example.com", "My Subject", "Line 1\nLine 2")

    assert len(calls) == 1
    url, json_data, headers, timeout = calls[0]
    assert url == "https://api.resend.com/emails"
    assert headers["Authorization"] == "Bearer re_test_key"
    assert json_data["to"] == ["test@example.com"]
    assert json_data["subject"] == "My Subject"
    assert json_data["html"] == "Line 1<br/>Line 2"
    assert json_data["text"] == "Line 1\nLine 2"
