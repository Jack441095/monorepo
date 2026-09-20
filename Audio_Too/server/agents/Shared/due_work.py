"""Due and overdue work items shared by CLI agents and the dashboard."""

from __future__ import annotations

from datetime import date, datetime
from typing import Callable


def parse_record_date(value: object) -> date | None:
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def collect_due_items(
    list_records: Callable[[str], list[dict]],
    *,
    overdue_only: bool = False,
) -> list[dict]:
    today = date.today()
    items: list[dict] = []

    for record in list_records("projects"):
        if record.get("status", "Open") in {"Closed", "Complete", "Completed"}:
            continue
        due_value = record.get("follow_up") or record.get("deadline")
        parsed = parse_record_date(due_value)
        if overdue_only and (not parsed or parsed >= today):
            continue
        if not overdue_only and parsed and parsed > today:
            continue
        if due_value:
            items.append({
                "type": "project",
                "id": record.get("id"),
                "name": record.get("project") or record.get("client"),
                "due": due_value,
                "next_action": record.get("next_action") or record.get("waiting_on"),
                "overdue": bool(parsed and parsed < today),
            })

    for record in list_records("leads"):
        if record.get("status", "New") in {"Closed", "Not interested"}:
            continue
        due_value = record.get("follow_up")
        parsed = parse_record_date(due_value)
        if overdue_only and (not parsed or parsed >= today):
            continue
        if not overdue_only and parsed and parsed > today:
            continue
        if due_value:
            items.append({
                "type": "lead",
                "id": record.get("id"),
                "name": record.get("lead"),
                "due": due_value,
                "next_action": record.get("next_action"),
                "overdue": bool(parsed and parsed < today),
            })

    for record in list_records("followups"):
        if record.get("status", "Open") in {"Done", "Closed", "Complete", "Completed"}:
            continue
        due_value = record.get("due")
        parsed = parse_record_date(due_value)
        if overdue_only and (not parsed or parsed >= today):
            continue
        if not overdue_only and parsed and parsed > today:
            continue
        if due_value:
            items.append({
                "type": record.get("owner") or "followup",
                "id": record.get("id"),
                "name": record.get("subject"),
                "due": due_value,
                "next_action": record.get("notes"),
                "overdue": bool(parsed and parsed < today),
            })

    items.sort(key=lambda item: (not item.get("overdue"), str(item.get("due", ""))))
    return items
