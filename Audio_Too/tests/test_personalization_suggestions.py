"""Tests for wiring learned personalization suggestions into Thursday's replies.

docs/CAPABILITY_IMPROVEMENTS_2026-07-06.md: user_profile.get_suggestions()
correctly tracks frequent requests and frequent clients, but nothing called
it — a neighboring mechanism (get_suggested_sequences) was already wired in;
this one specifically was never connected. thursday/orchestrator.py now
appends the top personalization suggestion when nothing else already
offered a next step.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import thursday.user_profile as user_profile  # noqa: E402
from thursday.orchestrator import handle  # noqa: E402
from thursday.session_manager import get_or_create_session  # noqa: E402


def _fresh_profile_id() -> str:
    return "sugg-test-" + uuid.uuid4().hex[:8]


def test_get_suggestions_excludes_daily_briefing_when_already_shown() -> None:
    profile_id = _fresh_profile_id()
    user_profile.mark_briefing_shown(profile_id)
    suggestions = user_profile.get_suggestions(profile_id)
    assert "Start with a daily briefing" not in suggestions


def test_frequent_request_produces_a_suggestion() -> None:
    profile_id = _fresh_profile_id()
    user_profile.mark_briefing_shown(profile_id)  # keep the briefing suggestion out of the way
    for _ in range(3):
        user_profile.record_request("invoices", profile_id=profile_id)
    suggestions = user_profile.get_suggestions(profile_id)
    assert any("invoices" in s.lower() for s in suggestions)


def test_handle_appends_personal_suggestion_when_nothing_else_offered() -> None:
    profile_id = _fresh_profile_id()
    user_profile.mark_briefing_shown(profile_id)
    user_profile.update_preference("daily_briefing", False, profile_id=profile_id)
    for _ in range(3):
        user_profile.record_request("invoices", profile_id=profile_id)

    session = get_or_create_session("sugg-session-" + uuid.uuid4().hex[:8])
    session["context"]["profile_id"] = profile_id

    result = handle("show me the invoices", session=session, list_records=lambda _t: [])

    assert "*Suggestion:*" in result
    assert "invoices" in result.lower()


def test_handle_does_not_duplicate_daily_briefing_suggestion() -> None:
    """The literal 'Start with a daily briefing' suggestion is redundant
    with the separate daily_briefing() mechanism, so it must never appear
    as a *Suggestion:* line even when it's the top learned suggestion."""
    profile_id = _fresh_profile_id()
    # Do NOT mark the briefing as shown — it would normally be suggestion #1.
    session = get_or_create_session("sugg-session-" + uuid.uuid4().hex[:8])
    session["context"]["profile_id"] = profile_id

    result = handle("show me the invoices", session=session, list_records=lambda _t: [])

    assert "Start with a daily briefing" not in result
