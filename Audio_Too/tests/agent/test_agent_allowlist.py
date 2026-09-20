"""Tests for dashboard agent command restrictions."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "business" / "agents"))

from Shared.agent_router import dashboard_command_allowed  # noqa: E402


def test_blocks_invoice_writes() -> None:
    allowed, message = dashboard_command_allowed("Admin", ["save-invoice", "client: Sam"], "client: Sam")
    assert not allowed
    assert "not allowed" in message.lower()


def test_allows_list_clients() -> None:
    allowed, message = dashboard_command_allowed("Admin", ["clients"], "")
    assert allowed
    assert message == "clients"


def test_auto_resolves_to_allowed_email() -> None:
    allowed, message = dashboard_command_allowed(
        "Admin",
        ["auto", "draft a follow-up email to the mixing client"],
        "draft a follow-up email to the mixing client",
    )
    assert allowed
    assert message == "email"
