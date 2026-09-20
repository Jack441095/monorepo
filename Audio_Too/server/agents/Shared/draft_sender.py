"""Draft send simulator for Audio_Too.

Marks drafts as sent and creates follow-up reminders through the shared service.
External SMTP delivery is handled only by the durable outbox worker.
"""

from __future__ import annotations

from typing import Callable

from app.api_schemas import DraftSendRequest
from app.draft_service import DraftNotFound, DraftNotSendable
from app.draft_service import send_draft as send_draft_service


def _format_send_result(result: dict) -> str:
    draft = result["draft"]
    if result.get("already_sent"):
        return f"Draft {draft['id']} was already sent (status: Sent)."
    followup = result["followup"]
    return "\n".join(
        [
            "✉️ Draft Sent",
            "=" * 35,
            f"  Type: {draft.get('type', 'message')}",
            f"  To: {draft.get('recipient', 'Unknown')}",
            f"  Subject: {draft.get('subject', '')}",
            "  Status: Pending/Approved → Sent",
            f"  Follow-up: {followup.get('due', '')} (+7 days)",
            f"\n  Draft ID: {draft['id']}",
        ]
    )


def send_draft(
    _list_records: Callable[[str], list[dict]],
    _add_record: Callable[[str, dict], dict],
    _update_record: Callable,
    draft_id: str,
    *,
    use_email: bool = False,
) -> str:
    """Send a draft through the shared transactional service.

    The legacy use_email flag is rejected; external delivery must use the outbox.
    Returns a summary string.
    """
    if use_email:
        return "Direct email is disabled; queue a reviewed external delivery in the dashboard."
    try:
        _status, result = send_draft_service(
            DraftSendRequest.from_payload({"id": draft_id})
        )
    except DraftNotFound:
        return f"Draft not found: {draft_id}"
    except DraftNotSendable as exc:
        return str(exc)

    lines = [_format_send_result(result)]

    return "\n".join(lines)


def send_all_approved(
    list_records: Callable[[str], list[dict]],
    add_record: Callable[[str, dict], dict],
    update_record: Callable,
) -> str:
    """Send all approved drafts at once."""
    drafts = list_records("drafts")
    approved = [d for d in drafts if (d.get("status") or "").lower() == "approved"]

    if not approved:
        return "No approved drafts to send."

    results: list[str] = []
    for d in approved:
        send_draft(list_records, add_record, update_record, d["id"])
        results.append(f"  - {d.get('recipient', '?')}: {d.get('subject', '')[:50]}... \u2192 Sent")

    return (
        f"\u2709\ufe0f Sent {len(approved)} Approved Draft(s)\n"
        f"{'=' * 35}\n" +
        "\n".join(results) +
        "\n\nFollow-up reminders created for +7 days from now."
    )


def pending_since(list_records: Callable[[str], list[dict]]) -> str:
    """Show how long drafts have been sitting in pending status."""
    drafts = list_records("drafts")
    pending = [d for d in drafts if (d.get("status") or "").lower() == "pending"]

    if not pending:
        return "No pending drafts."

    from datetime import datetime

    lines = ["\u23f3 Pending Drafts Age Report", "=" * 40]
    now = datetime.now()

    for d in pending:
        created = d.get("created_at", "")
        days_ago = "?"
        if created:
            try:
                created_dt = datetime.strptime(created[:10], "%Y-%m-%d")
                days_ago = str((now - created_dt).days)
            except ValueError:
                pass

        recipient = d.get("recipient", "?")
        subject = d.get("subject", "")[:50]
        dtype = d.get("type", "?")
        lines.append(f"  {d['id']:>8}  {days_ago:>4}d  [{dtype:<12}] {recipient:<20} {subject}")

    return "\n".join(lines)


def check_and_deliver_autonomous(draft: dict, list_records, add_record, update_record) -> str | None:
    """If autonomous mode is enabled: resolves recipient email, marks Approved, queues and sends."""
    import os
    if os.environ.get("AUDIO_TOO_AUTONOMOUS") != "1":
        return None

    recipient = draft.get("recipient", "")
    email = None
    
    # 1. Resolve client name to email if it's not already an email
    if recipient and "@" not in recipient:
        try:
            clients = list_records("clients")
            for c in clients:
                if c.get("name") and recipient.lower() in c["name"].lower():
                    if c.get("email") and "@" in c["email"]:
                        email = c["email"]
                        break
        except Exception:
            pass
    elif recipient and "@" in recipient:
        email = recipient

    # 2. Update recipient if resolved
    if email and email != recipient:
        draft["recipient"] = email
        update_record("drafts", draft["id"], {"recipient": email})

    # 3. Mark Approved
    draft["status"] = "Approved"
    update_record("drafts", draft["id"], {"status": "Approved"})

    # 4. Queue delivery
    if email:
        try:
            from app.delivery_service import queue_draft_delivery
            from app.api_schemas import DraftDeliveryRequest
            queue_draft_delivery(DraftDeliveryRequest(draft_id=draft["id"], recipient_email=email))
            
            # 5. Process immediately via the delivery worker
            from app.delivery_worker import process_one
            import uuid
            worker_id = f"subagent-auto-{uuid.uuid4().hex[:8]}"
            process_one(worker_id=worker_id)
            
            return f"\n\n⚡ Autonomous Mode: Email queued and sent to {email}."
        except Exception as e:
            return f"\n\n⚡ Autonomous Mode: Failed to queue delivery: {e}"
    
    return "\n\n⚡ Autonomous Mode: Approved (no recipient email to deliver)."
