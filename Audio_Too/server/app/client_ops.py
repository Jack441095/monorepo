"""Client intake and project readiness helpers for dashboard ops."""

from __future__ import annotations

from datetime import datetime

from db import add_record, list_records


def _clean(value: object) -> str:
    return str(value or "").strip()


def _lower(value: object) -> str:
    return _clean(value).lower()


def _missing_enquiry_fields(enquiry: dict) -> list[str]:
    missing: list[str] = []
    if not _clean(enquiry.get("name")):
        missing.append("name")
    if not _clean(enquiry.get("email")):
        missing.append("email")
    if _lower(enquiry.get("service")) in {"", "audio service", "other"}:
        missing.append("specific service")
    if not _clean(enquiry.get("deadline")):
        missing.append("deadline")
    if len(_clean(enquiry.get("message"))) < 40:
        missing.append("project brief")
    return missing


def _readiness_status(missing: list[str], blockers: list[str]) -> str:
    if blockers:
        return "blocked"
    if missing:
        return "needs-info"
    return "ready"


def intake_queue(limit: int = 12) -> list[dict]:
    out: list[dict] = []
    for enquiry in list_records("enquiries"):
        status = _lower(enquiry.get("status")) or "new"
        if status not in {"new", "open", "contacted"}:
            continue
        missing = _missing_enquiry_fields(enquiry)
        service = _clean(enquiry.get("service")) or "Audio service"
        action = (
            f"Ask for {', '.join(missing)}."
            if missing
            else "Reply with availability, rough process, and next steps."
        )
        out.append(
            {
                "id": _clean(enquiry.get("id")),
                "name": _clean(enquiry.get("name")) or "New enquiry",
                "email": _clean(enquiry.get("email")),
                "service": service,
                "deadline": _clean(enquiry.get("deadline")),
                "status": _clean(enquiry.get("status")) or "New",
                "missing": missing,
                "readiness": "ready" if not missing else "needs-info",
                "next_action": action,
                "created_at": _clean(enquiry.get("created_at")),
            }
        )
    return out[: max(1, min(50, limit))]


def _matching_invoice(project: dict, invoices: list[dict]) -> dict | None:
    client = _lower(project.get("client"))
    service = _lower(project.get("service"))
    for invoice in invoices:
        if client and client in _lower(invoice.get("client")):
            return invoice
        if service and service in _lower(invoice.get("service")):
            return invoice
    return None


def _deadline_state(deadline: str) -> str:
    text = _clean(deadline)
    if not text or text.startswith("["):
        return "missing"
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            due = datetime.strptime(text, fmt)
        except ValueError:
            continue
        days = (due.date() - datetime.now().date()).days
        if days < 0:
            return "overdue"
        if days <= 7:
            return "due-soon"
        return "scheduled"
    return "noted"


def project_readiness(limit: int = 20) -> list[dict]:
    invoices = list_records("invoices")
    out: list[dict] = []
    closed = {"closed", "complete", "completed", "delivered"}
    for project in list_records("projects"):
        if _lower(project.get("status")) in closed:
            continue
        missing: list[str] = []
        blockers: list[str] = []
        if not _clean(project.get("client")):
            missing.append("client")
        if not _clean(project.get("service")):
            missing.append("service")
        if not _clean(project.get("deadline")) or _clean(project.get("deadline")).startswith("["):
            missing.append("deadline")
        if not _clean(project.get("next_action")):
            missing.append("next action")
        waiting_on = _clean(project.get("waiting_on"))
        if waiting_on and waiting_on.lower() not in {"owner review", "owner reply", "none", "n/a"}:
            blockers.append(f"waiting on {waiting_on}")
        invoice = _matching_invoice(project, invoices)
        invoice_status = _clean(invoice.get("status")) if invoice else ""
        if not invoice:
            missing.append("invoice")
        elif invoice_status.lower() not in {"paid", "sent"}:
            blockers.append(f"invoice {invoice_status or 'not sent'}")
        deadline_state = _deadline_state(_clean(project.get("deadline")))
        if deadline_state == "overdue":
            blockers.append("deadline overdue")
        status = _readiness_status(missing, blockers)
        out.append(
            {
                "id": _clean(project.get("id")),
                "project": _clean(project.get("project")) or _clean(project.get("service")) or "Project",
                "client": _clean(project.get("client")),
                "service": _clean(project.get("service")),
                "status": _clean(project.get("status")),
                "deadline": _clean(project.get("deadline")),
                "deadline_state": deadline_state,
                "missing": missing,
                "blockers": blockers,
                "readiness": status,
                "next_action": _clean(project.get("next_action")) or "Set the next project action.",
            }
        )
    order = {"blocked": 0, "needs-info": 1, "ready": 2}
    out.sort(key=lambda item: (order.get(item["readiness"], 9), item["deadline_state"] != "overdue", item["project"].lower()))
    return out[: max(1, min(100, limit))]


def snapshot() -> dict:
    intake = intake_queue()
    readiness = project_readiness()
    return {
        "ok": True,
        "intake": intake,
        "readiness": readiness,
        "summary": {
            "new_enquiries": len(intake),
            "blocked_projects": sum(1 for item in readiness if item["readiness"] == "blocked"),
            "needs_info": sum(1 for item in readiness if item["readiness"] == "needs-info"),
            "ready": sum(1 for item in readiness if item["readiness"] == "ready"),
        },
    }


def draft_enquiry_reply(enquiry_id: str) -> dict:
    enquiry = next((item for item in list_records("enquiries") if _clean(item.get("id")) == enquiry_id), None)
    if not enquiry:
        return {"ok": False, "error": "Enquiry not found."}
    missing = _missing_enquiry_fields(enquiry)
    name = _clean(enquiry.get("name")) or "there"
    service = _clean(enquiry.get("service")) or "your project"
    if missing:
        questions = "\n".join(f"- {item.capitalize()}" for item in missing)
        body = (
            f"Hi {name},\n\nThanks for getting in touch about {service}.\n\n"
            "Before I quote properly, could you send a little more detail on:\n"
            f"{questions}\n\nOnce I have that, I can suggest the best next step and turnaround.\n\nBest,\nAudio_Too"
        )
    else:
        body = (
            f"Hi {name},\n\nThanks for the details about {service}.\n\n"
            "This looks workable. The next step is to confirm the source files, deadline, references, "
            "and delivery format, then I can send a clear quote and upload link.\n\nBest,\nAudio_Too"
        )
    draft = add_record(
        "drafts",
        {
            "type": "message",
            "recipient": _clean(enquiry.get("email")) or name,
            "subject": f"Re: {service} enquiry",
            "body": body,
            "status": "Pending",
            "source": "client_intake_agent",
        },
    )
    return {"ok": True, "draft": draft, "message": f"Draft reply created for {name}."}
