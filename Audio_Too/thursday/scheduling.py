"""Calendar & Time Intelligence — natural datetime parsing, scheduling,
daily briefings, and macOS Calendar integration for Thursday.

Provides Thursday with awareness of time, dates, and schedules so it can
answer questions like:
  - "What's on my calendar today?"
  - "Remind me Thursday at 3pm to send Jordan the stems"
  - "Schedule a session with Sarah next Tuesday at 2pm"
  - "What does my week look like?"
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from thursday.atomic_io import atomic_write

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))
from action_policy import action_allowed, action_denied_message  # noqa: E402

from thursday.runtime_paths import CALENDAR_DIR
REMINDERS_FILE = CALENDAR_DIR / "reminders.json"
AGENDA_FILE = CALENDAR_DIR / "agenda_cache.json"


# ─── Natural Language Date/Time Parsing ─────────────────────────────────


def parse_datetime(text: str, reference: datetime | None = None) -> dict:
    """Parse natural datetime from text.

    Returns a dict with:
      - datetime: resolved datetime object (or None)
      - is_recurring: bool
      - is_relative: bool
      - time_str: original time expression
      - date_str: original date expression
      - weekday: resolved weekday name (if applicable)
      - day_part: time-of-day classification
    """
    ref = reference or datetime.now()
    text_lower = text.lower().strip()

    result = {
        "datetime": None,
        "is_recurring": False,
        "is_relative": False,
        "time_str": None,
        "date_str": None,
        "weekday": None,
        "day_part": None,
    }

    # Detect day parts
    day_part_patterns = [
        (r"\bmorning\b", "morning"),
        (r"\bafternoon\b", "afternoon"),
        (r"\bevening\b", "evening"),
        (r"\bnight\b", "night"),
        (r"\blunch\b", "lunch"),
        (r"\bmidnight\b", "night"),
        (r"\bnoon\b", "afternoon"),
    ]
    for pattern, part in day_part_patterns:
        if re.search(pattern, text_lower):
            result["day_part"] = part
            break

    # Time expressions
    time_patterns = [
        (r"(\d{1,2})[.:](\d{2})\s*(am|pm)?", lambda m: _parse_time(m.group(1), m.group(2), m.group(3))),
        (r"(\d{1,2})\s*(am|pm)\b", lambda m: _parse_time(m.group(1), "00", m.group(2))),
        (r"\bat\s+(\d{1,2})\b(?!\s*:\d{2})", lambda m: _parse_time(m.group(1), "00", None)),
    ]
    resolved_time = None
    for pattern, handler in time_patterns:
        m = re.search(pattern, text_lower)
        if m:
            try:
                resolved_time = handler(m)
            except (ValueError, IndexError):
                continue
            if resolved_time:
                result["time_str"] = m.group(0).strip()
                break

    # Relative date expressions
    relative_patterns = [
        (r"\btoday\b", 0),
        (r"\btonight\b", 0),
        (r"\btomorrow\b", 1),
        (r"\bday after tomorrow\b", 2),
        (r"\byesterday\b", -1),
        (r"\bnext\s+week\b", 7),
        (r"\blast\s+week\b", -7),
        (r"\bin\s+(\d+)\s+days?\b", lambda m: int(m.group(1))),
        (r"\bin\s+(\d+)\s+weeks?\b", lambda m: int(m.group(1)) * 7),
    ]
    resolved_date = None
    for pattern, delta in relative_patterns:
        m = re.search(pattern, text_lower)
        if m:
            days = delta(m) if callable(delta) else delta
            resolved_date = ref + timedelta(days=days)
            result["is_relative"] = True
            result["date_str"] = m.group(0).strip()
            break

    # Weekday expressions
    weekday_map = {
        "monday": 0, "mon": 0,
        "tuesday": 1, "tue": 1, "tues": 1,
        "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3, "thur": 3,
        "friday": 4, "fri": 4,
        "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6,
    }
    weekday_patterns = [
        (r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lambda m: _next_weekday(m.group(1), ref, weekday_map)),
        (r"\blast\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lambda m: _last_weekday(m.group(1), ref, weekday_map)),
        (r"\bthis\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lambda m: _this_weekday(m.group(1), ref, weekday_map)),
        (r"\b(on\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lambda m: _next_weekday(m.group(2), ref, weekday_map) if not resolved_date else resolved_date),
    ]
    for pattern, handler in weekday_patterns:
        m = re.search(pattern, text_lower)
        if m:
            candidate = handler(m)
            if candidate and not resolved_date:
                resolved_date = candidate
                result["weekday"] = m.group(2) if m.lastindex >= 2 else m.group(1)
                result["date_str"] = m.group(0).strip()
                break

    # Absolute date patterns: "March 15", "15th March", "2026-03-15"
    if not resolved_date:
        date_patterns = [
            (r"(\d{4})-(\d{1,2})-(\d{1,2})", lambda m: _try_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))),
            (r"(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?", lambda m: _try_date(ref.year, _month_num(m.group(1)), int(m.group(2)), ref)),
            (r"(\d{1,2})(?:st|nd|rd|th)\s+(\w+)", lambda m: _try_date(ref.year, _month_num(m.group(2)), int(m.group(1)), ref)),
        ]
        for pattern, handler in date_patterns:
            m = re.search(pattern, text_lower)
            if m:
                try:
                    candidate = handler(m)
                    if candidate:
                        resolved_date = candidate
                        result["date_str"] = m.group(0).strip()
                        break
                except (ValueError, IndexError):
                    continue

    # Fall back to today if only a time was given
    if resolved_time and not resolved_date:
        resolved_date = ref

    if resolved_date:
        hour, minute = (resolved_time or (9, 0)) if resolved_time else (9, 0)
        try:
            result["datetime"] = resolved_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except (ValueError, OverflowError):
            result["datetime"] = resolved_date

    # Recurring detection
    if re.search(r"\b(?:every|each|daily|weekly|monthly)\b", text_lower):
        result["is_recurring"] = True

    return result


def _parse_time(hour_str: str, minute_str: str, ampm: str | None) -> tuple[int, int] | None:
    """Parse time components into (hour, minute)."""
    try:
        hour = int(hour_str)
        minute = int(minute_str)
        if ampm:
            ampm = ampm.lower()
            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return (hour, minute)
    except (ValueError, TypeError):
        pass
    return None


def _month_num(name: str) -> int:
    """Convert month name to number."""
    months = {
        "january": 1, "jan": 1,
        "february": 2, "feb": 2,
        "march": 3, "mar": 3,
        "april": 4, "apr": 4,
        "may": 5,
        "june": 6, "jun": 6,
        "july": 7, "jul": 7,
        "august": 8, "aug": 8,
        "september": 9, "sep": 9,
        "october": 10, "oct": 10,
        "november": 11, "nov": 11,
        "december": 12, "dec": 12,
    }
    return months.get(name.lower(), 1)


def _try_date(year: int, month: int, day: int, reference: datetime | None = None) -> date | None:
    """Try to construct a date, handling year rollover."""
    try:
        if reference and year == reference.year and month < reference.month:
            # If month already passed this year, it's likely next year
            year += 1
        return date(year, month, day)
    except (ValueError, OverflowError):
        return None


def _next_weekday(name: str, ref: datetime, weekday_map: dict) -> datetime | None:
    """Get the next occurrence of a weekday from the reference."""
    target = weekday_map.get(name.lower())
    if target is None:
        return None
    days_ahead = target - ref.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return ref + timedelta(days=days_ahead)


def _last_weekday(name: str, ref: datetime, weekday_map: dict) -> datetime | None:
    """Get the last occurrence of a weekday from the reference."""
    target = weekday_map.get(name.lower())
    if target is None:
        return None
    days_behind = ref.weekday() - target
    if days_behind <= 0:
        days_behind += 7
    return ref - timedelta(days=days_behind)


def _this_weekday(name: str, ref: datetime, weekday_map: dict) -> datetime | None:
    """Get this week's occurrence of a weekday."""
    target = weekday_map.get(name.lower())
    if target is None:
        return None
    # This week: go back to Monday, then forward to target
    monday = ref - timedelta(days=ref.weekday())
    candidate = monday + timedelta(days=target)
    if candidate < ref:
        candidate += timedelta(days=7)  # Next week if already passed
    return candidate


# ─── Reminder Storage ────────────────────────────────────────────────────


def _load_reminders() -> list[dict]:
    """Load reminders from local storage."""
    if REMINDERS_FILE.exists():
        try:
            return json.loads(REMINDERS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


# reminders.json grew unboundedly forever -- acknowledging a reminder only
# flipped a flag, never removed it (unlike monitor.py's alerts, capped at
# [-50:], and diagnostics.py's analytics, capped at [-1000]/[-100]). Prune
# acknowledged reminders past this retention window on every save; leave
# unacknowledged ones untouched regardless of age since those still need
# action.
ACKNOWLEDGED_REMINDER_RETENTION_DAYS = 30


def _prune_old_acknowledged_reminders(reminders: list[dict]) -> list[dict]:
    cutoff = datetime.now() - timedelta(days=ACKNOWLEDGED_REMINDER_RETENTION_DAYS)
    kept = []
    for r in reminders:
        if not r.get("acknowledged"):
            kept.append(r)
            continue
        try:
            created_at = datetime.fromisoformat(r.get("created_at", ""))
        except ValueError:
            kept.append(r)  # unparseable timestamp -- keep rather than risk losing data
            continue
        if created_at >= cutoff:
            kept.append(r)
    return kept


def _save_reminders(reminders: list[dict]) -> None:
    """Save reminders to local storage."""
    CALENDAR_DIR.mkdir(parents=True, exist_ok=True)
    reminders = _prune_old_acknowledged_reminders(reminders)
    try:
        atomic_write(REMINDERS_FILE, json.dumps(reminders, indent=2))
    except OSError:
        pass


def schedule_reminder(
    text: str,
    when: str,
    session: dict | None = None,
    add_record: Callable | None = None,
) -> str:
    """Create a reminder/follow-up record.

    Args:
        text: The reminder description.
        when: Natural language time expression.
        session: Optional session dict for context.
        add_record: Data access function for persistence.

    Returns:
        Confirmation message.
    """
    parsed = parse_datetime(when)
    reminder = {
        "id": str(uuid.uuid4())[:12],
        "text": text,
        "created_at": datetime.now().isoformat(),
        "due_at": parsed["datetime"].isoformat() if parsed["datetime"] else None,
        "is_recurring": parsed["is_recurring"],
        "weekday": parsed["weekday"],
        "day_part": parsed["day_part"],
        "acknowledged": False,
        "session_id": session.get("session_id") if session else None,
    }

    # Try to persist via database
    if add_record:
        try:
            result = add_record("followups", {
                "owner": "thursday",
                "subject": f"Reminder: {text[:100]}",
                "due": parsed["datetime"].isoformat()[:10] if parsed["datetime"] else None,
                "notes": f"Created by Thursday. Parsed from: '{when}'",
                "status": "Open",
            })
            if result:
                reminder["db_id"] = result.get("id")
        except Exception:
            pass

    # Also store locally
    reminders = _load_reminders()
    reminders.append(reminder)
    _save_reminders(reminders)

    due_str = parsed["datetime"].strftime("%A %d %B at %H:%M") if parsed["datetime"] else when
    return f"Reminder set: {text} — {due_str}"


def get_due_reminders(days: int = 1) -> list[dict]:
    """Get reminders due within the next N days."""
    reminders = _load_reminders()
    now = datetime.now()
    cutoff = now + timedelta(days=days)
    due = []
    for r in reminders:
        if r.get("acknowledged"):
            continue
        due_at = r.get("due_at")
        if due_at:
            try:
                dt = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
                if dt.tzinfo:
                    dt = dt.replace(tzinfo=None)
                if now <= dt <= cutoff:
                    due.append(r)
            except (ValueError, TypeError):
                continue
        else:
            # No specific date — always show
            due.append(r)
    return due


def acknowledge_reminder(reminder_id: str) -> bool:
    """Mark a reminder as acknowledged."""
    reminders = _load_reminders()
    for r in reminders:
        if r.get("id") == reminder_id:
            r["acknowledged"] = True
            _save_reminders(reminders)
            return True
    return False


# ─── Agenda Building ─────────────────────────────────────────────────────


def agenda_for_day(target_date: str | date | None = None) -> str:
    """Get a formatted agenda for a given day.

    Args:
        target_date: Date string (YYYY-MM-DD), date object, or None for today.

    Returns:
        Formatted agenda text.
    """
    if target_date is None:
        dt = datetime.now()
    elif isinstance(target_date, str):
        try:
            dt = datetime.fromisoformat(target_date)
        except (ValueError, TypeError):
            dt = datetime.now()
    elif isinstance(target_date, date) and not isinstance(target_date, datetime):
        dt = datetime.combine(target_date, datetime.min.time())
    else:
        dt = target_date

    lines = [f"📅 Agenda for {dt.strftime('%A, %d %B %Y')}"]
    lines.append("=" * 45)

    # Due reminders
    reminders = get_due_reminders(days=0)
    day_reminders = [r for r in reminders if _is_same_day(r.get("due_at", ""), dt)]
    if day_reminders:
        lines.append("\nReminders:")
        for r in day_reminders:
            due = r.get("due_at", "")
            time_str = ""
            if due:
                try:
                    due_dt = datetime.fromisoformat(due.replace("Z", "+00:00"))
                    time_str = due_dt.strftime(" at %H:%M")
                except (ValueError, TypeError):
                    pass
            lines.append(f"  - {r['text']}{time_str}")
    else:
        lines.append("\nNo reminders for today.")

    return "\n".join(lines)


def agenda_for_week(start_date: str | None = None) -> str:
    """Get a formatted agenda for the week.

    Args:
        start_date: Optional start date string (YYYY-MM-DD). Defaults to today.

    Returns:
        Formatted week agenda.
    """
    if start_date:
        try:
            start = datetime.fromisoformat(start_date)
        except (ValueError, TypeError):
            start = datetime.now()
    else:
        start = datetime.now()

    # Go to Monday of this week
    monday = start - timedelta(days=start.weekday())

    lines = [f"📅 Week of {monday.strftime('%d %B %Y')}"]
    lines.append("=" * 50)

    all_reminders = get_due_reminders(days=7)

    for i in range(7):
        day = monday + timedelta(days=i)
        day_str = day.strftime("%A %d %B")
        day_reminders = [r for r in all_reminders if _is_same_day(r.get("due_at", ""), day)]

        if day_reminders:
            lines.append(f"\n{day_str}:")
            for r in day_reminders:
                due = r.get("due_at", "")
                time_str = ""
                if due:
                    try:
                        due_dt = datetime.fromisoformat(due.replace("Z", "+00:00"))
                        time_str = due_dt.strftime(" %H:%M")
                    except (ValueError, TypeError):
                        pass
                lines.append(f"  - {r['text']}{time_str}")
        else:
            lines.append(f"\n{day_str}: —")

    return "\n".join(lines)


def _is_same_day(due_str: str, dt: datetime) -> bool:
    """Check if a due datetime string falls on the same day as dt."""
    if not due_str:
        return False
    try:
        due_dt = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
        if due_dt.tzinfo:
            due_dt = due_dt.replace(tzinfo=None)
        return due_dt.date() == dt.date()
    except (ValueError, TypeError):
        return False


# ─── macOS Calendar Integration ──────────────────────────────────────────


def _run_applescript(script: str) -> str:
    """Run an AppleScript command and return stdout."""
    if not action_allowed("desktop_automation"):
        return f"Error: {action_denied_message('desktop_automation')}"
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )
        return (result.stdout or "").strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        logger.exception("Calendar automation failed")
        return "Calendar automation failed (error code: service_unavailable)."


def macos_read_calendar(days: int = 7) -> list[dict]:
    """Read macOS Calendar events for the next N days.

    Returns a list of {title, start_date, end_date, calendar, location}.
    """
    script = f"""
    tell application "Calendar"
        set allEvents to {{}}
        set targetDate to (current date)
        set endDate to targetDate + ({days} * days)
        repeat with cal in calendars
            set calEvents to every event of cal whose start date ≥ targetDate and start date ≤ endDate
            repeat with e in calEvents
                set end of allEvents to {{title:summary of e, start_date:start date of e, end_date:end date of e, calendar:title of cal}}
            end repeat
        end repeat
        return allEvents
    end tell
    """
    output = _run_applescript(script)
    if output.startswith("Error"):
        return []
    # Parse the text-based output into dicts
    events = []
    for line in output.split(","):
        if "title:" in line:
            events.append({"title": line.replace("title:", "").strip(), "source": "macos_calendar"})
    return events


def macos_add_event(title: str, start_date: datetime, end_date: datetime | None = None, calendar: str = "Audio_Too") -> dict:
    """Add an event to macOS Calendar.

    Args:
        title: Event title.
        start_date: Start datetime.
        end_date: End datetime (defaults to 1 hour later).
        calendar: Calendar name to use.

    Returns:
        Result dict.
    """
    if end_date is None:
        end_date = start_date + timedelta(hours=1)

    date_fmt = "%d/%m/%Y %H:%M"
    script = f"""
    tell application "Calendar"
        set cal to calendar "{calendar}"
        set newEvent to make new event at cal with properties {{summary:"{title}", start date:(date "{start_date.strftime(date_fmt)}"), end date:(date "{end_date.strftime(date_fmt)}")}}
        return id of newEvent
    end tell
    """
    output = _run_applescript(script)
    if output.startswith("Error"):
        return {"ok": False, "error": output}
    return {"ok": True, "event_id": output, "title": title}


def macos_list_calendars() -> list[str]:
    """List available macOS Calendar names."""
    script = """
    tell application "Calendar"
        set calNames to {}
        repeat with cal in calendars
            set end of calNames to title of cal
        end repeat
        return calNames
    end tell
    """
    output = _run_applescript(script)
    if output.startswith("Error"):
        return []
    # Parse comma-separated list
    return [c.strip() for c in output.split(",") if c.strip()]


def macos_reminder(title: str, due_date: datetime | None = None) -> dict:
    """Create a macOS Reminder.

    Args:
        title: Reminder text.
        due_date: Optional due date.

    Returns:
        Result dict.
    """
    if due_date:
        date_fmt = "%d/%m/%Y %H:%M"
        date_clause = f"with due date (date \"{due_date.strftime(date_fmt)}\")"
    else:
        date_clause = ""

    script = f"""
    tell application "Reminders"
        set newReminder to make new reminder with properties {{name:"{title}" {date_clause}}}
        return id of newReminder
    end tell
    """
    output = _run_applescript(script)
    if output.startswith("Error"):
        return {"ok": False, "error": output}
    return {"ok": True, "id": output}


# ─── Daily Briefing ──────────────────────────────────────────────────────


def daily_briefing(
    list_records: Callable | None = None,
    user_profile: dict | None = None,
) -> str:
    """Generate a daily briefing with agenda, alerts, and key info.

    Args:
        list_records: Data access function for business records.
        user_profile: User preferences dict.

    Returns:
        Formatted briefing text.
    """
    now = datetime.now()
    profile = user_profile or {}
    name = profile.get("user_name", "")

    # Time-based greeting
    hour = now.hour
    if hour < 12:
        greeting = f"Good morning{', ' + name if name else ''}."
    elif hour < 17:
        greeting = f"Good afternoon{', ' + name if name else ''}."
    else:
        greeting = f"Good evening{', ' + name if name else ''}."

    lines = [greeting]
    lines.append("")

    # Day info
    lines.append(f"Today is {now.strftime('%A, %d %B %Y')}.")
    lines.append("")

    # Agenda
    agenda = agenda_for_day()
    lines.append(agenda)

    # Business alerts (if list_records available)
    if list_records:
        try:
            from thursday.monitor import get_pending_alerts
            alerts = get_pending_alerts()
            if alerts:
                lines.append("")
                lines.append(f"You have {len(alerts)} pending alert(s):")
                for a in alerts[:3]:
                    lines.append(f"  - {a.get('message', '')}")
        except ImportError:
            pass

    lines.append("")
    lines.append("Ready when you are.")

    return "\n".join(lines)


def extract_event_details(text: str) -> tuple[str, str]:
    """Extract event title and time expression from natural language query.

    Example:
      "schedule session with Jordan on Friday at 3pm" -> ("session with Jordan", "Friday at 3pm")
    """
    text_lower = text.lower().strip()

    # Strip wake word if present at start
    for ww in ["hey thursday,", "hey thursday", "thursday,", "thursday"]:
        if text_lower.startswith(ww):
            text = text[len(ww):].strip()
            text_lower = text.lower().strip()
            break

    # Strip common command prefixes
    prefixes = [
        "schedule a session with ", "schedule an appointment with ",
        "schedule a meeting with ", "schedule a ", "schedule an ", "schedule ",
        "book a session with ", "book a meeting with ", "book a ", "book in ", "book ",
        "add a ", "add an ", "add ", "put ", "create a ", "create an ", "create "
    ]
    cleaned = text.strip()
    for pref in prefixes:
        if text_lower.startswith(pref):
            cleaned = text[len(pref):]
            break

    # Strip common calendar suffixes
    suffixes = [" to the calendar", " to my calendar", " on my calendar", " in my calendar"]
    for suff in suffixes:
        if cleaned.lower().endswith(suff):
            cleaned = cleaned[:-len(suff)]
            break

    # Look for splitting keywords: "on", "at", "for"
    # Common date indicators: "today", "tomorrow", "next",
    # "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
    indicators = [
        "today", "tomorrow", "next",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
    ]

    words = cleaned.split()
    split_idx = -1

    for i, word in enumerate(words):
        word_clean = word.lower().strip(",.!?")
        # Check if the word is a date indicator or is on/at/for followed by something
        if word_clean in indicators or word_clean in ["on", "at", "for"]:
            split_idx = i
            break

    if split_idx != -1:
        title = " ".join(words[:split_idx]).strip(",.!? ")
        when = " ".join(words[split_idx:]).strip(",.!? ")
    else:
        title = cleaned.strip(",.!? ")
        when = "today"  # default to today

    # Clean up calendar suffixes from title if they got split into it
    for suff in suffixes:
        if title.lower().endswith(suff):
            title = title[:-len(suff)].strip()

    # Clean up title if it ended up empty
    if not title:
        title = cleaned.strip(",.!? ")
        when = "today"

    if title:
        title = title[0].upper() + title[1:]

    return title, when

