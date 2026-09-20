"""Proactive reminder system for Audio_Too agents.

Aggregates due/overdue/stale items across all record types and provides
a unified "what needs attention" view that the CLI and dashboard can use.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable

from Shared.activity_log import log_event


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today() -> date:
    return date.today()


def parse_date(value: object) -> date | None:
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        parts = text.split("-")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def format_date_relative(d: date) -> str:
    """Return a human-friendly relative date string."""
    delta = (d - today()).days
    if delta < 0:
        return f"{abs(delta)} day{'s' if abs(delta) > 1 else ''} overdue"
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    return f"in {delta} days"


def days_ago(value: object) -> int | None:
    """Return number of days since a date string, or None if unparseable."""
    d = parse_date(value)
    if not d:
        return None
    return (today() - d).days


def time_since_created(created_at: str) -> str:
    """Return human-friendly time since a created_at timestamp."""
    d = parse_date(created_at)
    if not d:
        return "recently"
    delta = (today() - d).days
    if delta < 0:
        return "in the future"
    if delta == 0:
        return "today"
    if delta == 1:
        return "yesterday"
    if delta < 7:
        return f"{delta} days ago"
    weeks = delta // 7
    return f"{weeks} week{'s' if weeks > 1 else ''} ago"


def collect_reminders(list_records: Callable[[str], list[dict]]) -> dict:
    """Collect all reminders grouped by urgency.

    Returns:
        {
            "overdue": [...],   # Past due dates
            "today": [...],     # Due today
            "this_week": [...], # Due within 7 days (excluding today)
            "future": [...],    # Due beyond 7 days
            "stale": [...],     # No activity in 14+ days
        }
    """
    today_d = today()
    one_week = today_d + timedelta(days=7)
    two_weeks_ago = today_d - timedelta(days=14)

    reminders: dict[str, list[dict]] = {
        "overdue": [],
        "today": [],
        "this_week": [],
        "future": [],
        "stale": [],
    }

    seen_ids: set[str] = set()

    def add_reminder(
        group: str,
        kind: str,
        item_id: str,
        name: str,
        detail: str,
        due: str,
        created: str | None = None,
    ):
        dedup_key = f"{kind}:{item_id}"
        if dedup_key in seen_ids:
            return
        seen_ids.add(dedup_key)
        rec = {
            "type": kind,
            "id": item_id,
            "name": name,
            "detail": detail,
            "due": due,
            "created": created or "",
        }
        if group in reminders:
            reminders[group].append(rec)

    # 1. Followups table — open items sorted by due
    for record in list_records("followups"):
        status = (record.get("status") or "Open").strip().lower()
        if status in {"done", "closed", "complete", "completed"}:
            continue
        due_val = record.get("due", "")
        parsed = parse_date(due_val)
        subject = record.get("subject") or "Untitled"
        notes = record.get("notes") or ""
        item_id = record.get("id", "")

        if not parsed:
            continue

        group = categorize_date(parsed, today_d, one_week)
        add_reminder(group, "followup", item_id, subject, notes, due_val, record.get("created_at"))

    # 2. Projects with waiting_on or follow_up
    for record in list_records("projects"):
        status = (record.get("status") or "Open").strip().lower()
        if status in {"closed", "complete", "completed", "done"}:
            continue

        client = record.get("client") or "Unknown"
        project = record.get("project") or "Untitled"
        waiting_on = record.get("waiting_on") or ""
        follow_up = record.get("follow_up") or ""
        deadline = record.get("deadline") or ""
        item_id = record.get("id", "")
        name = f"{client}/{project}"

        # Check follow_up date
        if follow_up:
            parsed = parse_date(follow_up)
            if parsed:
                group = categorize_date(parsed, today_d, one_week)
                detail = f"Follow-up: {waiting_on}" if waiting_on else "Follow-up"
                add_reminder(group, "project", item_id, name, detail, follow_up, record.get("created_at"))

        # Check deadline
        if deadline:
            parsed = parse_date(deadline)
            if parsed:
                group = categorize_date(parsed, today_d, one_week)
                detail = f"Deadline: {waiting_on}" if waiting_on else "Deadline"
                add_reminder(group, "project-deadline", f"{item_id}-dl", name, detail, deadline, record.get("created_at"))

        # Check for staleness (no follow_up set or old follow_up)
        if not follow_up:
            updated = record.get("updated_at") or record.get("created_at") or ""
            d = parse_date(updated)
            if d and d < two_weeks_ago:
                add_reminder(
                    "stale", "project-stale", f"{item_id}-stale", name,
                    f"Waiting on: {waiting_on or 'nothing recorded'} — no update in {days_ago(updated)} days",
                    updated,
                    record.get("created_at"),
                )
        else:
            parsed = parse_date(follow_up)
            if parsed and parsed < two_weeks_ago:
                add_reminder(
                    "stale", "project-stale", f"{item_id}-stale", name,
                    f"Follow-up was {format_date_relative(parsed)} — may need attention",
                    follow_up,
                    record.get("created_at"),
                )

    # 3. Leads with follow_up
    for record in list_records("leads"):
        status = (record.get("status") or "New").strip().lower()
        if status in {"closed", "not interested"}:
            continue

        lead_name = record.get("lead") or "Unknown"
        follow_up = record.get("follow_up") or ""
        score = record.get("score") or 0
        item_id = record.get("id", "")
        name = f"{lead_name} (score: {score})"

        if follow_up:
            parsed = parse_date(follow_up)
            if parsed:
                group = categorize_date(parsed, today_d, one_week)
                next_action = record.get("next_action") or "Follow-up"
                add_reminder(group, "lead", item_id, name, next_action, follow_up, record.get("created_at"))

        # Stale leads (no follow_up or old follow_up)
        if not follow_up and status not in {"closed", "not interested"}:
            created = record.get("created_at") or ""
            d = parse_date(created)
            if d and d < two_weeks_ago:
                add_reminder(
                    "stale", "lead-stale", f"{item_id}-stale", name,
                    f"No follow-up set — created {time_since_created(created)}",
                    created,
                    created,
                )
        elif follow_up:
            parsed = parse_date(follow_up)
            if parsed and parsed < two_weeks_ago:
                add_reminder(
                    "stale", "lead-stale", f"{item_id}-stale", name,
                    f"Follow-up was {format_date_relative(parsed)} — lead may have gone cold",
                    follow_up,
                    record.get("created_at"),
                )

    # 4. Draft invoices older than 7 days
    for record in list_records("invoices"):
        inv_status = (record.get("status") or "").strip().lower()
        if inv_status not in {"draft"}:
            continue
        created = record.get("created_at") or ""
        d = parse_date(created)
        if d and d < two_weeks_ago:
            client_name = record.get("client") or "Unknown"
            total = record.get("total") or 0
            add_reminder(
                "stale", "invoice-draft", record.get("id", ""),
                f"Invoice for {client_name}",
                f"£{float(total):.2f} — draft created {time_since_created(created)}",
                created,
                created,
            )

    # Sort within each group by due date ascending
    for group in reminders:
        reminders[group].sort(key=lambda r: r.get("due", ""))

    return reminders


def categorize_date(parsed: date, today_d: date, one_week: date) -> str:
    if parsed < today_d:
        return "overdue"
    if parsed == today_d:
        return "today"
    if parsed <= one_week:
        return "this_week"
    return "future"


def format_reminders(reminders: dict) -> str:
    """Format reminders dict into a human-readable string."""
    parts = []

    group_labels = {
        "overdue": "\U0001f534 Overdue",
        "today": "\U0001f7e1 Due Today",
        "this_week": "\U0001f535 Due This Week",
        "future": "\u26aa Future",
        "stale": "\u274c Stale / Needs Attention",
    }

    has_any = False
    for group, label in group_labels.items():
        items = reminders.get(group, [])
        if not items:
            continue
        has_any = True
        parts.append(f"\n{label} ({len(items)}):")
        for item in items[:10]:  # Show max 10 per group
            due_str = item.get("due", "")
            detail = item.get("detail", "")
            name = item.get("name", "")
            kind = item.get("type", "")
            line = f"  - [{kind}] {name}"
            if detail:
                line += f" — {detail}"
            if due_str:
                line += f" ({due_str})"
            parts.append(line)
        if len(items) > 10:
            parts.append(f"  ... and {len(items) - 10} more")

    if not has_any:
        parts.append("\n\u2705 All clear! No reminders.")

    return "\n".join(parts)


def schedule_reminder(
    add_record: Callable[[str, dict], dict],
    text: str,
) -> dict:
    """Schedule a quick reminder from natural language.

    Understands patterns like:
    - "Check in with Jordan in 3 days"
    - "Follow up with Sarah on Friday"
    - "Send invoice to Mike tomorrow"
    """
    import re

    lowered = text.lower()
    due_date = today() + timedelta(days=7)  # Default: 7 days

    # Try "in N days/weeks"
    match = re.search(r"in\s+(\d+)\s*(day|days|week|weeks?)\b", lowered)
    if match:
        num = int(match.group(1))
        unit = match.group(2)
        if unit.startswith("week"):
            due_date = today() + timedelta(weeks=num)
        else:
            due_date = today() + timedelta(days=num)

    # Try "on Friday", "next week", "tomorrow"
    if not re.search(r"in\s+\d+", lowered):
        if "tomorrow" in lowered:
            due_date = today() + timedelta(days=1)
        elif "next week" in lowered:
            due_date = today() + timedelta(weeks=1)
        else:
            day_names = {
                "monday": 0, "tuesday": 1, "wednesday": 2,
                "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
            }
            for name, idx in day_names.items():
                if name in lowered:
                    today_idx = today().weekday()
                    days_ahead = idx - today_idx
                    if days_ahead <= 0:
                        days_ahead += 7
                    due_date = today() + timedelta(days=days_ahead)
                    break

    # Clean the subject
    subject = text.strip()
    subject = re.sub(
        r"\s+in\s+\d+\s+(day|days|week|weeks)\b",
        "",
        subject,
        flags=re.I,
    ).strip()

    record = add_record("followups", {
        "owner": "reminder",
        "subject": subject,
        "status": "Open",
        "due": due_date.isoformat(),
        "notes": f"Created by ./agent remind on {now()}",
    })

    log_event("reminder_created", f"{record.get('id')}: {subject}", actor="agent")
    return record


def find_stale_leads(list_records: Callable[[str], list[dict]]) -> list[dict]:
    """Find leads that haven't been contacted in 14+ days."""
    today_d = today()
    two_weeks_ago = today_d - timedelta(days=14)
    stale: list[dict] = []

    for record in list_records("leads"):
        status = (record.get("status") or "New").strip().lower()
        if status in {"closed", "not interested"}:
            continue

        follow_up = record.get("follow_up") or ""
        created = record.get("created_at") or ""

        is_stale = False
        reason = ""

        if not follow_up:
            d = parse_date(created)
            if d and d < two_weeks_ago:
                is_stale = True
                days_since = (today_d - d).days
                reason = f"No follow-up set, created {days_since} days ago"
        else:
            d = parse_date(follow_up)
            if d and d < two_weeks_ago:
                is_stale = True
                days_since = (today_d - d).days
                reason = f"Follow-up was {days_since} days ago"

        if is_stale:
            stale.append({
                "lead": record.get("lead", "Unknown"),
                "status": record.get("status", "New"),
                "score": record.get("score", 0),
                "service_fit": record.get("service_fit", ""),
                "source": record.get("source", ""),
                "reason": reason,
                "follow_up": follow_up or "(not set)",
                "id": record.get("id", ""),
            })

    stale.sort(key=lambda r: r.get("score", 0), reverse=True)
    return stale


def find_stale_projects(list_records: Callable[[str], list[dict]]) -> list[dict]:
    """Find projects with no updates in 14+ days."""
    today_d = today()
    two_weeks_ago = today_d - timedelta(days=14)
    stale: list[dict] = []

    for record in list_records("projects"):
        status = (record.get("status") or "Open").strip().lower()
        if status in {"closed", "complete", "completed", "done"}:
            continue

        follow_up = record.get("follow_up") or ""
        updated = record.get("updated_at") or record.get("created_at") or ""

        is_stale = False
        reason = ""

        if not follow_up:
            d = parse_date(updated)
            if d and d < two_weeks_ago:
                is_stale = True
                days_since = (today_d - d).days
                reason = f"No follow-up set, last update {days_since} days ago"
        else:
            d = parse_date(follow_up)
            if d and d < two_weeks_ago:
                is_stale = True
                days_since = (today_d - d).days
                reason = f"Follow-up was {days_since} days ago"

        if is_stale:
            stale.append({
                "project": record.get("project", "Untitled"),
                "client": record.get("client", "Unknown"),
                "status": record.get("status", "Open"),
                "waiting_on": record.get("waiting_on", ""),
                "service": record.get("service", ""),
                "reason": reason,
                "follow_up": follow_up or "(not set)",
                "id": record.get("id", ""),
            })

    stale.sort(key=lambda r: r.get("project", ""))
    return stale


def format_stale_leads(leads: list[dict]) -> str:
    if not leads:
        return "\nNo stale leads found. All leads have recent activity."
    parts = ["\U0001f50d Stale Leads (no contact in 14+ days):"]
    for lead in leads:
        parts.append(
            f"  - {lead['lead']} | score: {lead['score']} | status: {lead['status']} | "
            f"{lead['service_fit'] or 'no service'} | {lead['reason']}"
        )
        parts.append(f"    Follow-up: {lead['follow_up']}")
    parts.append(f"\nTotal: {len(leads)} stale lead{'s' if len(leads) > 1 else ''}")
    return "\n".join(parts)


def format_stale_projects(projects: list[dict]) -> str:
    if not projects:
        return "\nNo stale projects found."
    parts = ["\U0001f50d Stale Projects (no updates in 14+ days):"]
    for proj in projects:
        parts.append(
            f"  - {proj['client']}/{proj['project']} | {proj['service']} | "
            f"waiting on: {proj['waiting_on'] or 'nothing'} | {proj['reason']}"
        )
        parts.append(f"    Follow-up: {proj['follow_up']}")
    parts.append(f"\nTotal: {len(projects)} stale project{'s' if len(projects) > 1 else ''}")
    return "\n".join(parts)
