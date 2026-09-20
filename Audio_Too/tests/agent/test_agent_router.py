"""Tests for Shared/agent_router.py's request routing.

This module previously had zero unit test coverage (flagged in
docs/BACKLOG.md and confirmed in docs/CODEBASE_AUDIT_2026-07-06.md), and a
real misrouting bug was found within minutes of testing it directly: generic
Admin nouns ("client", "mastering") could outscore a specific Marketing
action word ("offer"), silently routing a marketing request to Admin.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "business" / "agents"))

from Shared.agent_router import normalize_args, route_request  # noqa: E402


def test_marketing_action_word_wins_over_generic_admin_nouns() -> None:
    """Regression test for the verified misrouting bug: a request naming a
    specific marketing action must route to Marketing even when it also
    contains more Admin-hint nouns than Marketing-hint nouns."""
    folder, args = route_request("Send a mastering offer to the new client")
    assert folder == "Marketing"
    assert args[0] == "offer"


def test_social_and_campaign_requests_route_to_marketing() -> None:
    folder, args = route_request("Run a social media campaign for the new artist")
    assert folder == "Marketing"
    assert args[0] in {"post", "campaign"}


def test_outreach_request_routes_to_marketing() -> None:
    folder, args = route_request("Add a new lead for outreach")
    assert folder == "Marketing"
    assert args[0] == "outreach"


def test_plain_admin_request_routes_to_admin() -> None:
    folder, args = route_request("Draft an invoice for the mastering session")
    assert folder == "Admin"
    assert args[0] == "auto"


def test_scheduling_request_routes_to_admin() -> None:
    folder, args = route_request("Schedule a mixing session with Sam")
    assert folder == "Admin"
    assert args[0] == "auto"


def test_normalize_args_resolves_admin_aliases() -> None:
    assert normalize_args("Admin", ["projects"]) == ["list-projects"]
    assert normalize_args("Admin", ["follow-up"]) == ["followups"]


def test_normalize_args_resolves_marketing_aliases() -> None:
    assert normalize_args("Marketing", ["leads"]) == ["list-leads"]
    assert normalize_args("Marketing", ["follow-ups"]) == ["followups"]


def test_normalize_args_defaults_to_help_when_empty() -> None:
    assert normalize_args("Admin", []) == ["--help"]
