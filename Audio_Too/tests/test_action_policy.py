"""Deny-by-default tests for external action policy."""

from __future__ import annotations

import pytest

import action_policy


@pytest.mark.parametrize("action, variable", action_policy.ACTION_FLAGS.items())
def test_external_actions_are_disabled_by_default(monkeypatch, action: str, variable: str) -> None:
    monkeypatch.delenv(variable, raising=False)
    assert action_policy.action_allowed(action) is False


def test_only_the_specific_action_flag_enables_capability(monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_ALLOW_EXTERNAL_EMAIL", "1")
    assert action_policy.action_allowed("external_email") is True
    assert action_policy.action_allowed("daw_control") is False
