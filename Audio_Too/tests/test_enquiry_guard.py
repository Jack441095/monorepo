"""Tests for public enquiry validation."""

from __future__ import annotations

import pytest

from enquiry_guard import (
    HoneypotError,
    clear_rate_limit,
    is_honeypot,
    is_rate_limited,
    validate_enquiry_payload,
)


def test_validate_accepts_good_payload() -> None:
    result = validate_enquiry_payload(
        {
            "name": "Alex Producer",
            "email": "alex@example.com",
            "service": "Mixing",
            "message": "I need a mix for a single due next month.",
            "deadline": "June 2026",
        }
    )
    assert result["email"] == "alex@example.com"
    assert result["service"] == "Mixing"


def test_honeypot_raises() -> None:
    assert is_honeypot({"company_website": "https://spam.test"})
    with pytest.raises(HoneypotError):
        validate_enquiry_payload({"name": "Bot", "email": "a@b.co", "message": "x" * 25, "company_website": "x"})


def test_short_message_rejected() -> None:
    with pytest.raises(ValueError, match="20 and 5000"):
        validate_enquiry_payload({"name": "Alex", "email": "alex@example.com", "message": "too short"})


def test_rate_limit_blocks_after_max() -> None:
    address = ("203.0.113.50", 12345)
    for _ in range(5):
        assert is_rate_limited(address) is False
    assert is_rate_limited(address) is True


def test_login_rate_limit_can_be_cleared_after_success() -> None:
    address = ("192.0.2.44", 1234)
    for _ in range(8):
        assert is_rate_limited(address, scope="dashboard_login") is False
    assert is_rate_limited(address, scope="dashboard_login") is True

    clear_rate_limit(address, scope="dashboard_login")

    assert is_rate_limited(address, scope="dashboard_login") is False
