"""Tests for thursday/beta_invite_ops.py -- draft-only beta invite
composition (no sending capability, confirmed with the founder). Live-
reads real facts from the truth sheet rather than hardcoding them, but
deliberately never embeds the actual release SHA (it can change between
beta waves and this module can't verify which build any given email is
really attaching).
"""

from __future__ import annotations

import thursday.ops.beta_invite_ops as bio


def test_draft_is_clearly_marked_unsent():
    out = bio.draft_beta_invite("test@example.com")
    assert out.startswith("DRAFT — NOT SENT. Review and send manually.")


def test_draft_includes_real_recipient_email():
    out = bio.draft_beta_invite("jordan@example.com")
    assert "To: jordan@example.com" in out


def test_draft_uses_name_when_given():
    out = bio.draft_beta_invite("jordan@example.com", "Jordan")
    assert "Hi Jordan," in out


def test_draft_uses_generic_greeting_without_name():
    out = bio.draft_beta_invite("jordan@example.com")
    assert "Hi," in out
    assert "Hi ," not in out


def test_draft_never_embeds_a_specific_release_sha():
    out = bio.draft_beta_invite("jordan@example.com")
    # No hex-SHA-shaped token anywhere in the draft -- the founder must
    # attach and confirm the build themselves, per the module's stated
    # reasoning (a hardcoded SHA would go stale between beta waves).
    import re
    assert not re.search(r"\b[0-9a-f]{8,40}\b", out)
    assert "FOUNDER: attach the exact frozen release ZIP" in out


def test_draft_includes_gatekeeper_instructions():
    out = bio.draft_beta_invite("jordan@example.com")
    assert "Gatekeeper" in out
    assert "Right-click" in out


def test_draft_asks_for_file_safety_issues_first():
    out = bio.draft_beta_invite("jordan@example.com")
    assert "stop and tell me" in out


def test_draft_falls_back_honestly_when_truth_sheet_field_missing(monkeypatch):
    monkeypatch.setattr(bio, "_read_truth_sheet_field", lambda field: None)
    out = bio.draft_beta_invite("jordan@example.com")
    assert "not found live" in out


def test_read_truth_sheet_field_reads_real_version():
    version = bio._read_truth_sheet_field("Version")
    assert version is not None
    assert "0.2.0" in version


def test_read_truth_sheet_field_returns_none_for_unknown_field():
    assert bio._read_truth_sheet_field("Not A Real Field XYZ") is None


def test_feedback_template_path_exists_on_this_machine():
    # A live, non-mocked check -- confirms the cited path is real, not
    # just well-formed.
    assert bio.feedback_template_path().exists()
