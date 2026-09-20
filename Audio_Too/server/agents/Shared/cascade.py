"""Cascade follow-up system for Audio_Too.

Tracks where a lead is in their outreach sequence based on
how many drafts already exist for them and how many days have passed.
Suggests the next appropriate message.
"""

from __future__ import annotations

from datetime import date
from typing import Callable


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


def sequence_status(
    list_records: Callable[[str], list[dict]],
    lead_name: str,
) -> str:
    """Show where a lead is in their outreach sequence."""
    leads = list_records("leads")
    drafts = list_records("drafts")

    needle = lead_name.strip().lower()
    target_lead = None
    for lead in leads:
        if str(lead.get("lead", "")).lower() == needle or str(lead.get("id", "")).lower() == needle:
            target_lead = lead
            break

    if not target_lead:
        return f"Lead not found: {lead_name}"

    lead_label = target_lead.get("lead", "Unknown")
    status = target_lead.get("status", "New")
    score = target_lead.get("score", 0)
    service = target_lead.get("service_fit", "")
    follow_up = target_lead.get("follow_up", "")
    source = target_lead.get("source", "")

    # Find all drafts for this lead (by recipient name matching lead name)
    lead_drafts = [
        d for d in drafts
        if str(d.get("recipient", "")).lower() == needle
        or (str(d.get("subject", "")).lower().startswith(needle))
    ]
    # Also match by content containing the lead name
    if not lead_drafts:
        lead_drafts = [
            d for d in drafts
            if needle in str(d.get("recipient", "")).lower()
            or needle in str(d.get("body", "")).lower()
        ]

    # Categorise drafts by type
    message_count = len([d for d in lead_drafts if d.get("type") in ("outreach", "email")])
    outreach_drafts = [d for d in lead_drafts if d.get("type") in ("outreach", "email")]
    other_drafts = [d for d in lead_drafts if d.get("type") not in ("outreach", "email")]

    # Determine sequence stage
    days_since_first = 0
    first_message_date = None
    if outreach_drafts:
        dates = []
        for d in outreach_drafts:
            created = parse_date(d.get("created_at"))
            if created:
                dates.append(created)
        if dates:
            earliest = min(dates)
            first_message_date = earliest
            days_since_first = (today() - earliest).days

    # Sequence stages
    stages = {
        0: "No outreach sent yet. First contact needed.",
        1: "First outreach sent. Follow-up recommended after 7 days.",
        2: "Two messages sent. Consider a different angle or offer.",
        3: "Three messages sent. May be time for a direct call or final check.",
    }
    current_stage = min(message_count, 3)

    # Determine if follow-up is due
    follow_up_due = False
    follow_up_days = 0
    if follow_up:
        fd = parse_date(follow_up)
        if fd:
            follow_up_days = (today() - fd).days
            follow_up_due = follow_up_days > 0

    # Build output
    lines = [
        f"\U0001f504 Sequence Status: {lead_label}",
        "=" * 40,
        f"  Status: {status} | Score: {score} | Service: {service or 'Not set'} | Source: {source or 'Unknown'}",
        "",
        f"  Sequence stage: {current_stage}/3",
        f"  Messages sent: {message_count}",
        f"  Other drafts: {len(other_drafts)} (invoices, offers, etc.)",
    ]

    if first_message_date:
        lines.append(f"  First contact: {first_message_date.isoformat()} ({days_since_first} days ago)")

    if follow_up:
        lines.append(f"  Follow-up set: {follow_up}" +
                      (f" ({follow_up_days} day{'s' if follow_up_days > 1 else ''} overdue!)" if follow_up_due else ""))

    lines.append("")
    lines.append(f"  \U0001f4ac Recommendation: {stages[current_stage]}")

    if current_stage == 1 and follow_up_due:
        lines.append("  \u26a0\ufe0f  Follow-up is overdue. Consider sending Message 2 today.")
    elif current_stage == 1 and not follow_up_due:
        lines.append(f"  Next action: Draft follow-up message in {7 - follow_up_days} days if no response.")

    if current_stage == 2 and not follow_up:
        lines.append("  \u26a0\ufe0f  No follow-up date set. Schedule one to stay on track.")

    if current_stage >= 2:
        lines.append("  \U0001f4ad If no response after 3 messages, move to 'Not interested' or try a different channel.")

    # Show details of sent drafts
    if outreach_drafts:
        lines.append("")
        lines.append("  Messages sent:")
        for d in sorted(outreach_drafts, key=lambda x: x.get("created_at", "")):
            status_tag = d.get("status", "Pending")
            created = (d.get("created_at") or "")[:10]
            subject = d.get("subject", "(no subject)")
            lines.append(f"    - [{status_tag}] {created}: {subject}")

    return "\n".join(lines)
