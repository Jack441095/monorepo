"""Scheduled maintenance commands for Audio_Too.

Provides cron-daily and cron-weekly commands that can be run from
crontab, launchd, or manually.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from Shared.activity_log import log_event
from Shared.backup import run_backup
from Shared.data_store import export_json_snapshots, export_multi_sheet_xlsx
from Shared.reports import monthly_report


ROOT = Path(__file__).resolve().parent


def today() -> date:
    return date.today()


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def cron_daily(
    list_records: Callable[[str], list[dict]],
    add_record: Callable[[str, dict], dict],
) -> str:
    """Run once daily: overdue checks, stale detection, lead scoring, JSON snapshots.

    Designed to be run via crontab or launchd every morning.
    Returns a summary of what was done.
    """
    actions: list[str] = []

    # 1. Check overdue invoices — create a follow-up draft for each
    overdue_invoices = [
        inv for inv in list_records("invoices")
        if (inv.get("status") or "").lower() in {"sent", "overdue"}
    ]
    for inv in overdue_invoices:
        client = inv.get("client", "Unknown")
        total = inv.get("total", 0)
        add_record("followups", {
            "owner": "cron",
            "subject": f"Follow up on overdue invoice for {client} (\u00a3{float(total or 0):.2f})",
            "due": (today() + timedelta(days=1)).isoformat(),
            "notes": "Auto-created by cron-daily. Invoice was sent but not paid.",
            "status": "Open",
        })
    if overdue_invoices:
        actions.append(f"Created {len(overdue_invoices)} follow-up(s) for overdue invoices")

    # 2. Check stale leads and create suggested outreach followups
    leads = list_records("leads")
    stale_leads = [
        lead for lead in leads
        if (lead.get("status") or "New").lower() not in {"closed", "not interested"}
        and not lead.get("follow_up")
    ]
    for lead in stale_leads:
        lead_name = lead.get("lead", "Unknown")
        # Only create if no pending draft exists for this lead
        existing_drafts = [
            d for d in list_records("drafts")
            if d.get("type") == "outreach"
            and lead_name.lower() in str(d.get("recipient", "")).lower()
            and (d.get("status") or "").lower() == "pending"
        ]
        if not existing_drafts:
            add_record("drafts", {
                "type": "outreach",
                "recipient": lead_name,
                "subject": f"Follow-up: {lead.get('service_fit') or 'services'} for {lead_name}",
                "body": f"Hi {lead_name},\n\nJust checking in to see if you're still interested in {lead.get('service_fit') or 'our services'}.\n\nLet me know!\n\nAudio_Too",
                "status": "Pending",
                "source": "auto-cron",
            })
    if stale_leads:
        actions.append(f"Created {len(stale_leads)} outreach draft(s) for stale lead(s)")

    # 3. Re-score all leads using shared data store
    from Shared.data_store import update_record
    try:
        from Marketing.main import score_lead_record
    except ImportError:
        # Simple inline scoring
        def score_lead_record(r: dict) -> int:  # noqa: ANN206
            s = 20
            if r.get("contact"):
                s += 15
            if r.get("service_fit"):
                s += 15
            if r.get("source"):
                s += 10
            if r.get("next_action"):
                s += 10
            status = (r.get("status") or "").lower()
            if status == "warm":
                s += 20
            elif status == "hot":
                s += 35
            elif status in ("not interested", "closed"):
                s -= 30
            return max(0, min(100, s))
    updated = 0
    for lead in leads:
        new_score = score_lead_record(lead)
        if lead.get("score") != new_score:
            update_record("leads", lead.get("id", ""), {"score": new_score}, ["lead"])
            updated += 1
    if updated:
        actions.append(f"Re-scored {updated} lead(s)")

    # 4. Export JSON snapshots
    paths = export_json_snapshots()
    actions.append(f"Exported {len(paths)} JSON snapshot(s)")

    log_event("cron_daily", "; ".join(actions), actor="cron")

    lines = [
        "\U0001f4cb Daily Maintenance Complete",
        f"  Run at: {now()}",
        "",
    ]
    for action in actions:
        lines.append(f"  \u2705 {action}")
    if not actions:
        lines.append("  No actions needed.")
    lines.append(f"\n  {len(actions)} task(s) completed.")
    return "\n".join(lines)


def cron_weekly(
    list_records: Callable[[str], list[dict]],
    add_record: Callable[[str, dict], dict],
) -> str:
    """Run once weekly: weekly review + backup + full export workbook.

    Designed to be run via crontab or launchd every Monday morning.
    """
    actions: list[str] = []

    # 1. Generate and save weekly review
    try:
        report = monthly_report(list_records)
        outputs_dir = ROOT.parent / "Admin" / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        weekly_path = outputs_dir / f"weekly_review_{today().isoformat()}.txt"
        weekly_path.write_text(report, encoding="utf-8")
        actions.append(f"Saved weekly review to {weekly_path}")
    except Exception as e:
        actions.append(f"Weekly review skipped: {e}")

    # 2. Run backup
    try:
        backup_path = run_backup()
        actions.append(f"Backup created: {backup_path}")
    except Exception as e:
        actions.append(f"Backup failed: {e}")

    # 3. Generate full export workbook
    try:
        path = export_multi_sheet_xlsx(
            {
                "Clients": (["id", "name", "contact", "status", "notes"], list_records("clients")),
                "Projects": (["id", "project", "client", "service", "status", "deadline", "waiting_on", "follow_up"], list_records("projects")),
                "Invoices": (["id", "date", "client", "service", "hours", "rate", "total", "status", "notes"], list_records("invoices")),
                "Leads": (["id", "lead", "contact", "service_fit", "status", "score", "source", "next_action", "follow_up"], list_records("leads")),
                "Campaigns": (["id", "campaign", "audience", "service", "platforms", "status"], list_records("campaigns")),
                "Drafts": (["id", "type", "recipient", "subject", "status", "source", "created_at"], list_records("drafts")),
            },
            f"audio_too_weekly_{today().isoformat()}.xlsx",
        )
        actions.append(f"Workbook exported: {path}")
    except Exception as e:
        actions.append(f"Workbook export failed: {e}")

    # 4. Also run daily tasks
    cron_daily(list_records, add_record)
    actions.append("Daily maintenance included")

    log_event("cron_weekly", "; ".join(actions), actor="cron")

    lines = [
        "\U0001f4c5 Weekly Maintenance Complete",
        f"  Run at: {now()}",
        "",
    ]
    for action in actions:
        lines.append(f"  \u2705 {action}")
    lines.append(f"\n  {len(actions)} task(s) completed.")
    return "\n".join(lines)
