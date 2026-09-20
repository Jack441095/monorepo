"""Cross-agent workflow operations for Audio_Too.

Handles transitions between agent domains:
- Lead (Marketing) → Client (Admin) + Project (Admin)
- Enquiry (Website) → Client (Admin) + Project (Admin)
- Pipeline summary (end-to-end view)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from Shared.activity_log import log_event


def convert_lead_to_client_and_project(
    list_records: Callable[[str], list[dict]],
    add_record: Callable[[str, dict], dict],
    lead_id: str,
) -> dict:
    """Resolve a lead ID/name and delegate to the shared transactional service."""
    leads = list_records("leads")
    needle = lead_id.strip().lower()
    target = None
    for lead in leads:
        lead_id_val = str(lead.get("id", "")).lower()
        lead_name = str(lead.get("lead", "")).lower()
        if lead_id_val == needle or lead_name == needle:
            target = lead
            break

    if not target:
        return {
            "ok": False,
            "message": f"Lead not found: {lead_id}",
            "lead": None,
            "client": None,
            "project": None,
        }
    try:
        business_root = Path(__file__).resolve().parent.parent.parent
        sys.path.insert(0, str(business_root))
        sys.path.insert(0, str(business_root / "app"))
        from app.api_schemas import LeadConversionRequest
        from lead_service import LeadNotConvertible, LeadNotFound, convert_lead
    except ImportError:
        return {
            "ok": False,
            "message": "Could not import the Website lead service. Check that the module is accessible.",
            "lead": None,
            "client": None,
            "project": None,
        }
    try:
        _status, result = convert_lead(
            LeadConversionRequest.from_payload({"id": str(target["id"])})
        )
    except LeadNotFound:
        return {
            "ok": False,
            "message": "Conversion failed because the lead no longer exists.",
            "lead": None,
            "client": None,
            "project": None,
        }
    except LeadNotConvertible as exc:
        return {
            "ok": False,
            "message": str(exc),
            "lead": target,
            "client": None,
            "project": None,
        }
    if result.get("already_converted"):
        return {
            "ok": False,
            "message": f"Lead '{target.get('lead')}' is already converted.",
            "lead": result.get("lead"),
            "client": None,
            "project": None,
        }

    lead_name = str(target.get("lead") or "Unknown")
    lead_service = str(target.get("service_fit") or "General")
    log_event(
        "lead_converted",
        f"Lead '{lead_name}' → client ({result['client'].get('id')}) + project ({result['project'].get('id')})",
        actor="agent",
    )

    return {
        "ok": True,
        "message": (
            f"Converted lead '{lead_name}' into:\n"
            f"  Client: {lead_name} ({result['client'].get('id')})\n"
            f"  Project: {result['project'].get('project')} ({result['project'].get('id')})\n\n"
            f"Next steps:\n"
            f"  ./agent admin save-invoice \"Client: {lead_name} Service: {lead_service}\"\n"
            f"  ./agent admin email \"Send welcome message to {lead_name} about their {lead_service} project\""
        ),
        "lead": result.get("lead"),
        "client": result.get("client"),
        "project": result.get("project"),
    }


def pipeline_summary(
    list_records: Callable[[str], list[dict]],
) -> str:
    """Generate an end-to-end pipeline summary: leads → clients → projects → invoices."""
    leads = list_records("leads")
    clients = list_records("clients")
    projects = list_records("projects")
    invoices = list_records("invoices")

    # Lead funnel
    new_leads = [lead for lead in leads if (lead.get("status") or "New").lower() == "new"]
    warm_leads = [lead for lead in leads if (lead.get("status") or "").lower() == "warm"]
    hot_leads = [lead for lead in leads if (lead.get("status") or "").lower() == "hot"]
    closed_leads = [
        lead for lead in leads
        if (lead.get("status") or "").lower() in {"closed", "not interested"}
    ]

    # Projects
    active_projects = [p for p in projects if (p.get("status") or "Open").lower() not in {"closed", "complete", "completed", "done"}]
    completed_projects = [p for p in projects if (p.get("status") or "").lower() in {"closed", "complete", "completed", "done"}]

    # Invoices
    draft_invoices = [i for i in invoices if (i.get("status") or "").lower() == "draft"]
    sent_invoices = [i for i in invoices if (i.get("status") or "").lower() == "sent"]
    paid_invoices = [i for i in invoices if (i.get("status") or "").lower() == "paid"]

    # Revenue
    total_revenue = sum(float(i.get("total") or 0) for i in paid_invoices)
    outstanding = sum(float(i.get("total") or 0) for i in sent_invoices)
    draft_value = sum(float(i.get("total") or 0) for i in draft_invoices)

    # Conversion rates
    total_leads = len(leads)
    conversion_rate = 0.0
    if total_leads > 0:
        conversion_rate = (len(clients) / total_leads) * 100

    # Bottleneck detection
    bottlenecks = []
    if len(new_leads) > len(warm_leads) * 2 and len(warm_leads) > 0:
        bottlenecks.append("New leads aren't warming up. Consider more initial outreach.")
    if len(warm_leads) > len(hot_leads) * 2 and len(hot_leads) > 0:
        bottlenecks.append("Warm leads stuck. Try follow-ups with specific offers.")
    if len(hot_leads) > len(clients) and len(clients) > 0:
        bottlenecks.append("Hot leads not converting. Time for calls or in-person meetings.")
    if len(active_projects) > len(sent_invoices) + len(draft_invoices) and len(active_projects) > 2:
        bottlenecks.append("Projects without invoices. Make sure every project has a billing plan.")

    lines = [
        "\U0001f4ca Pipeline Summary",
        "",
        f"  Leads: {len(leads)} (\U0001f7e2 {len(new_leads)} new / \U0001f7e1 {len(warm_leads)} warm / \U0001f534 {len(hot_leads)} hot / \u26aa {len(closed_leads)} closed)",
        f"  \u2193 Conversion rate: {conversion_rate:.0f}%",
        f"  Clients: {len(clients)}",
        "  \u2193",
        f"  Projects: {len(active_projects)} active + {len(completed_projects)} completed",
        "  \u2193",
        f"  Invoices: {len(draft_invoices)} draft / {len(sent_invoices)} sent / {len(paid_invoices)} paid",
        f"  Revenue: \u00a3{total_revenue:.2f} paid | \u00a3{outstanding:.2f} outstanding | \u00a3{draft_value:.2f} in drafts",
    ]

    if bottlenecks:
        lines.append("")
        lines.append("  \u26a0\ufe0f Bottlenecks:")
        for b in bottlenecks:
            lines.append(f"    - {b}")

    return "\n".join(lines)


def convert_enquiry_to_client_and_project(
    list_records: Callable[[str], list[dict]],
    add_record: Callable[[str, dict], dict],
    enquiry_id: str,
) -> dict:
    """Convert a website enquiry through the shared transactional service."""
    try:
        business_root = Path(__file__).resolve().parent.parent.parent
        sys.path.insert(0, str(business_root))
        sys.path.insert(0, str(business_root / "app"))
        from app.api_schemas import EnquiryConversionRequest
        from enquiry_service import EnquiryNotFound, convert_enquiry
    except ImportError:
        return {
            "ok": False,
            "message": "Could not import the Website enquiry service. Check that the module is accessible.",
            "enquiry": None, "client": None, "project": None,
        }

    # Resolve ID to match Website module's lookup
    needle = enquiry_id.strip()
    matches = [e for e in list_records("enquiries") if str(e.get("id", "")) == needle]
    if not matches:
        matches = [e for e in list_records("enquiries") if e.get("name", "").strip().lower() == needle.lower()]
    if not matches:
        return {
            "ok": False,
            "message": f"Enquiry not found: {enquiry_id}",
            "enquiry": None, "client": None, "project": None,
        }

    target = matches[0]
    try:
        _status, result = convert_enquiry(
            EnquiryConversionRequest.from_payload({"id": str(target["id"])})
        )
    except EnquiryNotFound:
        return {"ok": False, "message": "Conversion failed.", "enquiry": None, "client": None, "project": None}
    if result.get("already_converted"):
        return {
            "ok": False,
            "message": f"Enquiry '{target.get('name')}' is already converted.",
            "enquiry": result.get("enquiry"),
            "client": None,
            "project": None,
        }

    name = target.get("name", "Unknown")
    service = target.get("service", "General")
    log_event("enquiry_converted",
              f"Enquiry '{name}' → client + project + lead",
              actor="agent")

    return {
        "ok": True,
        "message": (
            f"Converted enquiry from '{name}' into:\n"
            f"  Client: {result['client'].get('name')} ({result['client'].get('id')})\n"
            f"  Project: {result['project'].get('project')} ({result['project'].get('id')})\n"
            f"  Lead: {result['lead'].get('lead')} ({result['lead'].get('id')})\n\n"
            f"Next: ./agent admin email \"Reply to {name} about their {service} enquiry\""
        ),
        "enquiry": result.get("enquiry"),
        "client": result.get("client"),
        "project": result.get("project"),
    }
