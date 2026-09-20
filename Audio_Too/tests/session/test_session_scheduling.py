"""Tests for Shared/sessions.py natural-language session parsing.

This module had zero test coverage before docs/CODEBASE_AUDIT_2026-07-06.md
found and verified a real bug: the time-parsing regex matched the first 1-2
digit run anywhere in the text (including from a "2026-07-10" date), so
"Mix session with Sam on 2026-07-10 at 3pm" extracted time "20:00" instead of
"15:00" — which also silently defeated the double-booking conflict check.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "business" / "agents"))

from Shared.sessions import _parse_details, schedule_session  # noqa: E402


def test_time_is_not_corrupted_by_a_leading_iso_date() -> None:
    """Regression test for the verified bug: an ISO date before the time
    expression must not be mistaken for the hour."""
    details = _parse_details("Mix session with Sam on 2026-07-10 at 3pm for 2 hours")
    assert details["date"] == "2026-07-10"
    assert details["time"] == "15:00"


def test_bare_hour_with_am_pm_and_no_at_prefix() -> None:
    details = _parse_details("Mastering session with Jordan Friday 2pm 3 hours")
    assert details["time"] == "14:00"


def test_24_hour_colon_format_without_at_prefix() -> None:
    details = _parse_details("Recording with Alex 14:00")
    assert details["time"] == "14:00"


def test_no_time_mentioned_extracts_no_time() -> None:
    details = _parse_details("Mix session with Sam on 2026-07-10 for 2 hours")
    assert "time" not in details


def test_noon_and_midnight_am_pm_conversion() -> None:
    assert _parse_details("Session with Sam at 12pm")["time"] == "12:00"
    assert _parse_details("Session with Sam at 12am")["time"] == "00:00"


def test_lowercase_client_name_is_still_parsed_and_title_cased() -> None:
    """Regression (2026-08-02, live-tested): "schedule a session with sarah
    tomorrow at 2pm" -- completely ordinary lowercase typing, not a rare
    edge case -- previously failed to match at all (the name group required
    a capital first letter), falling through to a "Could not parse client
    name" error that sat confusingly next to a successful Action receipt
    from the orchestrator's confirmation-gate wrapper, since the wrapper has
    no way to know the handler's own return text was reporting a failure."""
    details = _parse_details("schedule a session with sarah tomorrow at 2pm")
    assert details["client"] == "Sarah"


def test_already_capitalized_client_name_is_unaffected() -> None:
    """Regression guard: must not change behaviour for the overwhelming
    common case of a properly-capitalized name, and must not mangle
    internal capitalization (e.g. "McDonald") by blindly title-casing."""
    details = _parse_details("Mix session with Sam on 2026-07-10 at 3pm")
    assert details["client"] == "Sam"

    details2 = _parse_details("Session with McDonald at 2pm")
    assert details2["client"] == "McDonald"


def test_schedule_session_succeeds_end_to_end_with_a_lowercase_name() -> None:
    message = schedule_session(
        list_records=lambda _table: [],
        add_record=lambda _table, details: {**details, "id": 1, "created_at": "2026-08-02"},
        text="schedule a session with sarah tomorrow at 2pm",
    )
    assert "Could not parse client name" not in message
    assert "Sarah" in message


def test_double_booking_conflict_is_detected_at_the_correct_time() -> None:
    """With the corrupted time ("20:00" instead of "15:00"), this conflict
    check would silently miss the collision."""
    existing = [
        {"client": "Sam", "date": "2026-07-10", "time": "15:00", "status": "Confirmed"}
    ]
    message = schedule_session(
        list_records=lambda _table: existing,
        add_record=lambda _table, _details: {**_details, "id": 1},
        text="Mix session with Jordan on 2026-07-10 at 3pm for 2 hours",
    )
    assert "conflict" in message.lower()
