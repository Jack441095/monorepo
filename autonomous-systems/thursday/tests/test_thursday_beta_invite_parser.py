"""Tests for thursday/beta_invite_ops.py's command parser."""

from __future__ import annotations

import pytest

import thursday.ops.beta_invite_ops as bio


def test_parse_colon_form_with_name():
    result = bio.parse_draft_beta_invite_command(
        "draft beta invite: jordan@example.com | name: Jordan"
    )
    assert result == ("jordan@example.com", {"recipient_name": "Jordan"})


def test_parse_for_form_no_name():
    result = bio.parse_draft_beta_invite_command("draft beta invite for jordan@example.com")
    assert result == ("jordan@example.com", {})


def test_parse_returns_none_for_unrelated_text():
    assert bio.parse_draft_beta_invite_command("what is the weather") is None
    assert bio.parse_draft_beta_invite_command("active tasks") is None


def test_parse_raises_on_empty_email():
    with pytest.raises(ValueError):
        bio.parse_draft_beta_invite_command("draft beta invite:")
