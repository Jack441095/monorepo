#!/usr/bin/env python3
"""FollowupAgent - Automated invoice follow-up and lead nurturing.

This agent runs on a schedule (daily) to:
1. Check unpaid invoices and schedule follow-ups
2. Score leads and auto-email warm ones
3. Archive cold leads after 60 days

Prerequisites:
- StatusTransitionService for invoice queries
- EmailNotify for sending emails
- AutonomousAgent base class
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Ensure Shared is importable
_SYSTEM_ROOT = Path(__file__).parent.parent.parent
_AGENT_SHARED = _SYSTEM_ROOT / "business" / "agents" / "Shared"
if str(_AGENT_SHARED) not in sys.path:
    sys.path.insert(0, str(_AGENT_SHARED))

from autonomous_base import AutonomousAgent

# Add app to path for database access
_APP_PATH = _SYSTEM_ROOT / "business" / "app"
if str(_APP_PATH) not in sys.path:
    sys.path.insert(0, str(_APP_PATH))

from db import connect, now
from email_notify import send_email, smtp_delivery_enabled


class FollowupAgent(AutonomousAgent):
    """Automated follow-up agent for revenue recovery and lead nurturing."""

    def __init__(self, root: Path | None = None, auto_approve: bool = False):
        super().__init__(root=root or _SYSTEM_ROOT, auto_approve=auto_approve)

    def check_invoice_followups(self) -> dict[str, Any]:
        """Daily check: find unpaid invoices and schedule follow-ups.
        
        Returns:
            Dict with followups_created, invoices_checked, and any errors
        """
        conn = connect()
        try:
            # Get invoices that are unpaid and past due
            invoices = conn.execute(
                """
                SELECT id, client_name, project_name, amount, sent_date, due_date
                FROM invoices 
                WHERE status = 'sent' 
                AND paid_date IS NULL
                ORDER BY due_date ASC
                """
            ).fetchall()
            
            followups = []
            for inv in invoices:
                days_overdue = (datetime.now() - datetime.fromisoformat(inv["sent_date"])).days
                
                if days_overdue >= 14:
                    # Escalate to manual intervention
                    followups.append({
                        "invoice_id": inv["id"],
                        "action": "escalate",
                        "reason": f"{days_overdue} days overdue - requires manual call",
                        "client": inv["client_name"],
                    })
                elif days_overdue >= 7:
                    # Draft phone script
                    result = self.run_task(
                        f"Draft phone follow-up script for {inv['client_name']} "
                        f"regarding overdue invoice {inv['id']} (${inv['amount']})"
                    )
                    followups.append({
                        "invoice_id": inv["id"],
                        "action": "phone_script_drafted",
                        "days_overdue": days_overdue,
                        "result": result,
                    })
                elif days_overdue >= 3:
                    # Draft reminder email
                    result = self.run_task(
                        f"Draft polite reminder email to {inv['client_name']} "
                        f"for invoice {inv['id']} - {inv['project_name']}"
                    )
                    if result.get("success"):
                        # Send the email
                        subject = f"Invoice Reminder: {inv['project_name']}"
                        body = result.get("synthesized_output", "")
                        if smtp_delivery_enabled() and inv.get("contact_email"):
                            send_email(
                                to=inv["contact_email"],
                                subject=subject,
                                text_body=body,
                            )
                    followups.append({
                        "invoice_id": inv["id"],
                        "action": "reminder_sent",
                        "days_overdue": days_overdue,
                    })
            
            return {
                "ok": True,
                "invoices_checked": len(invoices),
                "followups_created": len(followups),
                "followups": followups,
            }
        finally:
            conn.close()

    def score_and_nurture_leads(self) -> dict[str, Any]:
        """Weekly: score leads and auto-email warm ones.
        
        Scoring criteria:
        - Asked detailed questions (15 pts)
        - Multiple visits (10 pts each)
        - Email opened (5 pts)
        - Link clicked (10 pts)
        """
        conn = connect()
        try:
            leads = conn.execute(
                """
                SELECT id, name, email, question, created_at, last_seen
                FROM enquiries 
                WHERE status = 'new'
                ORDER BY created_at DESC
                """
            ).fetchall()
            
            nurtured = []
            for lead in leads:
                score = 5  # Base score for any enquiry
                
                # Score based on engagement
                if lead.get("question") and len(lead["question"]) > 50:
                    score += 15
                if lead.get("visit_count", 0) > 1:
                    score += lead["visit_count"] * 10
                if lead.get("email_opened"):
                    score += 5
                if lead.get("link_clicked"):
                    score += 10
                
                # Score threshold for auto-outreach
                if score >= 70:
                    result = self.run_task(
                        f"Draft personalized outreach to {lead['name']} "
                        f"about their interest in {lead.get('service_type', 'audio services')}"
                    )
                    if result.get("success"):
                        if smtp_delivery_enabled():
                            send_email(
                                to=lead["email"],
                                subject="Following up on your audio project enquiry",
                                text_body=result.get("synthesized_output", ""),
                            )
                        nurtured.append({
                            "lead_id": lead["id"],
                            "score": score,
                            "action": "email_sent",
                        })
            
            return {
                "ok": True,
                "leads_scored": len(leads),
                "nurtured": len(nurtured),
                "nurtured_leads": nurtured,
            }
        finally:
            conn.close()

    def archive_cold_leads(self, cutoff_days: int = 60) -> dict[str, Any]:
        """Archive leads with no engagement after cutoff period."""
        conn = connect()
        try:
            cutoff_date = (datetime.now() - timedelta(days=cutoff_days)).isoformat()
            
            archived = conn.execute(
                """
                UPDATE enquiries 
                SET status = 'archived'
                WHERE status = 'new' 
                AND created_at < ?
                AND (visit_count IS NULL OR visit_count < 2)
                """,
                (cutoff_date,)
            )
            
            return {
                "ok": True,
                "archived_count": archived.rowcount,
                "cutoff_days": cutoff_days,
            }
        finally:
            conn.close()


def main():
    """Run daily follow-up check."""
    agent = FollowupAgent()
    
    print("=== FollowupAgent Daily Check ===")
    print(f"Time: {now()}")
    
    # Check invoices
    inv_result = agent.check_invoice_followups()
    print(f"\nInvoices: {inv_result['invoices_checked']} checked, {inv_result['followups_created']} follow-ups")
    
    # Score leads (weekly on Mondays)
    if datetime.now().weekday() == 0:  # Monday
        lead_result = agent.score_and_nurture_leads()
        print(f"Leads: {lead_result['leads_scored']} scored, {lead_result['nurtured']} nurtured")
    
    # Archive cold leads
    archive_result = agent.archive_cold_leads()
    print(f"Archived: {archive_result['archived_count']} cold leads")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())