"""Session scheduling and management for Audio_Too.

Manages recording/mixing/mastering sessions with date, time, duration,
location, and rate tracking.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Callable


def _today() -> date:
    return date.today()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_details(text: str) -> dict:
    """Parse natural language session details from a text string.

    Extracts: client, project, service, date, time, duration, location, rate
    """
    result: dict = {}

    # Client — stop at known keywords
    stop_words = r"\b(friday|monday|tuesday|wednesday|thursday|saturday|sunday|tomorrow|at|on|for|service|project|rate|duration|hour|remote|studio|online|in.person|confirmed|tentative)\b"
    # Case-insensitive: found live-testing 2026-08-02, "schedule a session
    # with sarah tomorrow at 2pm" (lowercase, completely ordinary typing --
    # not a rare edge case) failed to match at all, since the name group
    # required a capital first letter. Fell through to the "Could not parse
    # client name" error path -- but with date/time still successfully
    # extracted, produced a genuinely confusing result: the error text sat
    # directly next to an "Action receipt", since the confirmation-gate
    # wrapper that appends the receipt has no way to know the handler's own
    # return string was actually reporting a failure, not a success.
    m = re.search(r"(?:client|with|for)\s+([A-Za-z][a-zA-Z'.-]+(?:\s+[A-Za-z][a-zA-Z'.-]+)?)", text)
    if m:
        name = m.group(1).strip()
        # Cut at stop words
        cut = re.search(stop_words, name, re.IGNORECASE)
        if cut:
            name = name[: cut.start()].strip()
        if name.islower():
            name = name.title()
        result["client"] = name

    # Project
    m = re.search(r"project[:\s]+(.+?)(?:\s+(?:service|date|time|duration|location|at|on|for|rate)|\s*$)", text, re.IGNORECASE)
    if m:
        result["project"] = m.group(1).strip()

    # Service
    services = {"mixing", "mastering", "recording", "editing", "production", "session", "vocal", "mix"}
    for svc in services:
        if svc in text.lower():
            result["service"] = svc.capitalize()
            break

    # Date - "Friday", "tomorrow", "next week", "2026-07-01"
    m = re.search(r"(?:on\s+)?(\d{4}-\d{2}-\d{2})", text)
    if m:
        result["date"] = m.group(1)
    else:
        # Day name
        day_names = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                     "friday": 4, "saturday": 5, "sunday": 6}
        for name, offset in day_names.items():
            if name in text.lower():
                today = _today()
                days_ahead = offset - today.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                result["date"] = (today + timedelta(days=days_ahead)).isoformat()
                break
        else:
            if "tomorrow" in text.lower():
                result["date"] = (_today() + timedelta(days=1)).isoformat()
            elif "next week" in text.lower():
                result["date"] = (_today() + timedelta(days=7)).isoformat()

    # Time - "2pm", "14:00", "at 2". Each alternative requires an explicit time
    # signal ("at ", a ":MM" part, or an am/pm suffix) rather than matching a
    # bare 1-2 digit number — the previous single optional-everything regex
    # matched the leading digits of a date like "2026-07-10" as the hour,
    # silently producing the wrong session time (see docs/CODEBASE_AUDIT_2026-07-06.md).
    time_patterns = (
        r"\bat\s+(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>a\.m\.|p\.m\.|am|pm)?\b",
        r"\b(?P<h>\d{1,2}):(?P<m>\d{2})\s*(?P<ap>a\.m\.|p\.m\.|am|pm)?\b",
        r"\b(?P<h>\d{1,2})\s*(?P<ap>a\.m\.|p\.m\.|am|pm)\b",
    )
    for pattern in time_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            break
    if m:
        groups = m.groupdict()
        hour = int(groups["h"])
        minute = int(groups.get("m") or 0)
        ampm = (groups.get("ap") or "").lower()
        if ampm.startswith("p") and hour < 12:
            hour += 12
        elif ampm.startswith("a") and hour == 12:
            hour = 0
        result["time"] = f"{hour:02d}:{minute:02d}"

    # Duration - "2 hours", "3h", "half day"
    m = re.search(r"(\d+)\s*(?:hour|hr|h)", text, re.IGNORECASE)
    if m:
        result["duration"] = f"{m.group(1)}h"
    elif "half day" in text.lower():
        result["duration"] = "4h"
    elif "full day" in text.lower():
        result["duration"] = "8h"

    # Location - "in person", "at studio", "remote", "online"
    if re.search(r"\bin[- ]?person\b", text, re.IGNORECASE) or "at studio" in text.lower():
        result["location"] = "Studio"
    elif "remote" in text.lower() or "online" in text.lower() or "zoom" in text.lower():
        result["location"] = "Remote"

    # Rate - "£45", "35 per hour", "rate: 50"
    m = re.search(r"(?:rate[:\s]*)?£(\d+)\b", text, re.IGNORECASE)
    if not m:
        m = re.search(r"\brate\s*[:\s]+\s*(\d+)\b", text, re.IGNORECASE)
    if not m:
        m = re.search(r"(?<!\d)(\d+)\s*(?:per\s*hour|gbp|£)\b", text, re.IGNORECASE)
    if m:
        result["rate"] = float(m.group(1))

    # Status defaults
    if "confirmed" in text.lower():
        result["status"] = "Confirmed"
    elif "tentative" in text.lower() or "maybe" in text.lower():
        result["status"] = "Tentative"
    else:
        result["status"] = "Scheduled"

    return result


def schedule_session(
    list_records: Callable[[str], list[dict]],
    add_record: Callable[[str, dict], dict],
    text: str,
) -> str:
    """Create a new session from natural language text."""
    details = _parse_details(text)

    if not details.get("client"):
        return (
            "Could not parse client name from the text.\n"
            'Try: ./agent schedule "Mix session with Jordan Friday 2pm 3 hours"\n'
            "Extracted fields: " + ", ".join(f"{k}={v}" for k, v in details.items())
        )

    # Check for double-booking on same date/time
    if details.get("date") and details.get("time"):
        existing = list_records("sessions")
        for s in existing:
            if s.get("date") == details.get("date") and s.get("time") == details.get("time"):
                if s.get("status", "").lower() not in {"cancelled", "done"}:
                    return (
                        f"\u26a0\ufe0f Conflict: {s.get('client')} already has a session "
                        f"on {details['date']} at {details['time']} ({s.get('status')}).\n"
                        "Choose a different time or date."
                    )

    record = add_record("sessions", details)

    lines = [
        "\U0001f4c5 Session Scheduled",
        f"{'=' * 35}",
        f"  Client: {record.get('client')}",
        f"  Date: {record.get('date') or 'Not specified'}",
        f"  Time: {record.get('time') or 'Not specified'}",
        f"  Duration: {record.get('duration') or 'Not specified'}",
    ]
    if details.get("service"):
        lines.append(f"  Service: {details.get('service')}")
    if details.get("location"):
        lines.append(f"  Location: {details.get('location')}")
    if details.get("rate"):
        lines.append(f"  Rate: \u00a3{float(details.get('rate', 0)):.2f}/hr")
    lines.append(f"  Status: {record.get('status')}")
    lines.append(f"\n  ID: {record.get('id')}")
    lines.append(f"  Created: {record.get('created_at')}")
    return "\n".join(lines)


def list_sessions(list_records: Callable[[str], list[dict]]) -> str:
    """List upcoming sessions sorted by date."""
    all_sessions = list_records("sessions")

    # Sort by date (with time as secondary sort)
    def sort_key(s: dict) -> str:
        return f"{s.get('date', '')} {s.get('time', '')}"

    all_sessions.sort(key=sort_key)

    today_str = _today().isoformat()

    upcoming = [s for s in all_sessions if s.get("date", "") >= today_str and s.get("status", "").lower() not in {"cancelled", "done"}]
    past = [s for s in all_sessions if s.get("date", "") < today_str or s.get("status", "").lower() in {"cancelled", "done"}]

    if not upcoming and not past:
        return "No sessions recorded yet."

    lines = ["\U0001f4c5 Sessions"]

    if upcoming:
        lines.append(f"\n\u25b6 Upcoming ({len(upcoming)}):")
        lines.append("-" * 40)
        for s in upcoming:
            date_str = s.get("date") or "TBD"
            time_str = s.get("time") or ""
            client = s.get("client") or "?"
            project = s.get("project") or ""
            duration = s.get("duration") or ""
            status = s.get("status") or ""
            status_tag = f" [{status}]" if status else ""
            project_str = f" — {project}" if project else ""
            duration_str = f" ({duration})" if duration else ""
            lines.append(f"  {date_str} {time_str}{duration_str} — {client}{project_str}{status_tag}")
    else:
        lines.append("\n  No upcoming sessions.")

    if past:
        lines.append(f"\n\U0001f4c4 Past ({len(past)}):")
        lines.append("-" * 40)
        for s in past[:5]:
            date_str = s.get("date") or "TBD"
            client = s.get("client") or "?"
            status = s.get("status") or ""
            lines.append(f"  {date_str} — {client} [{status}]")
        if len(past) > 5:
            lines.append(f"  ... and {len(past) - 5} more")

    return "\n".join(lines)


def show_session(
    list_records: Callable[[str], list[dict]],
    session_id: str,
) -> str:
    """Show full details of a single session."""
    all_sessions = list_records("sessions")
    needle = session_id.strip().lower()

    target = next(
        (s for s in all_sessions
         if s.get("id", "").lower() == needle
         or s.get("client", "").lower() == needle),
        None,
    )

    if not target:
        return f"Session not found: {session_id}"

    return (
        f"Session: {target.get('id')}\n"
        f"{'=' * 35}\n"
        f"  Client: {target.get('client') or 'Not set'}\n"
        f"  Project: {target.get('project') or 'Not set'}\n"
        f"  Service: {target.get('service') or 'Not set'}\n"
        f"  Date: {target.get('date') or 'Not set'}\n"
        f"  Time: {target.get('time') or 'Not set'}\n"
        f"  Duration: {target.get('duration') or 'Not set'}\n"
        f"  Location: {target.get('location') or 'Not specified'}\n"
        f"  Rate: \u00a3{float(target.get('rate', 0) or 0):.2f}/hr\n"
        f"  Status: {target.get('status') or 'Not set'}\n"
        f"  Notes: {target.get('notes') or 'None'}\n"
        f"  Created: {target.get('created_at') or 'Unknown'}"
    )


def cancel_session(
    list_records: Callable[[str], list[dict]],
    update_record: Callable,
    session_id: str,
) -> str:
    """Cancel a session."""
    all_sessions = list_records("sessions")
    needle = session_id.strip().lower()

    target = next(
        (s for s in all_sessions if s.get("id", "").lower() == needle), None
    )

    if not target:
        return f"Session not found: {session_id}"

    update_record("sessions", target["id"], {"status": "Cancelled"}, ["client", "project"])
    return f"Cancelled session: {target.get('client')} on {target.get('date')} at {target.get('time')}"
