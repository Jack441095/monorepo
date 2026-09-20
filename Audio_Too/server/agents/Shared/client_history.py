"""Client history timeline for Audio_Too.

Shows a chronological timeline of all interactions with a client:
projects, invoices, sessions, drafts, followups, expenses, leads, mix reviews
(since 2026-07-06, see docs/CAPABILITY_IMPROVEMENTS_2026-07-06.md), and (since
2026-07-08, see docs/AUDIT_FIX_EXECUTION_PLAN_2026-07-08.md Stage 3) AutoMix
jobs — asking about a client can now surface their mixdown job status
alongside their mix review and business records, not just business records.
"""

from __future__ import annotations

from typing import Callable


def _default_list_mix_reviews() -> list[dict]:
    """Lazy import — audio_analysis pulls in torch via analysis_features.py,
    and this timeline must not fail just because that's unavailable."""
    try:
        from audio_analysis.mix_review.mix_review import list_reviews

        return list_reviews(limit=200)
    except Exception:
        return []


def _default_list_automix_jobs() -> list[dict]:
    """Lazy import — automix_jobs lives in business/app, only on sys.path once
    thursday/client.py's setup has run; this timeline must not fail if not."""
    try:
        import automix_jobs

        return automix_jobs.list_recent_jobs(limit=200)
    except Exception:
        return []


def _in_range(event_date: str, date_range: tuple[str, str] | None) -> bool:
    """Inclusive (start, end) ISO-date-prefix check; no range means no filter."""
    if not date_range:
        return True
    start, end = date_range
    day = (event_date or "")[:10]
    return bool(day) and start <= day <= end


def _make_timeline_events(
    client_name: str,
    list_records: Callable[[str], list[dict]],
    *,
    list_mix_reviews: Callable[[], list[dict]] | None = None,
    list_automix_jobs: Callable[[], list[dict]] | None = None,
    date_range: tuple[str, str] | None = None,
) -> list[dict]:
    """Gather all records related to a client into a chronological timeline.

    date_range, when given, is an inclusive (start, end) ISO date pair —
    e.g. from thursday.resolver.temporal_date_range() — and drops events
    outside it ("what happened with Jordan last month").

    Returns sorted list of {date, type, summary, status} dicts.
    """
    needle = client_name.strip().lower()
    events: list[dict] = []

    # Projects
    client_project_ids: set[str] = set()
    for p in list_records("projects"):
        if needle in str(p.get("client", "")).lower():
            if p.get("id"):
                client_project_ids.add(str(p["id"]))
            events.append({
                "date": p.get("created_at", p.get("updated_at", "")),
                "type": "project",
                "summary": f"Project: {p.get('project', '?')} ({p.get('service', '?')}) — {p.get('status', 'Open')}",
                "status": p.get("status", ""),
                "id": p.get("id", ""),
            })

    # Invoices
    for inv in list_records("invoices"):
        if needle in str(inv.get("client", "")).lower():
            total = float(inv.get("total", 0) or 0)
            events.append({
                "date": inv.get("date", inv.get("created_at", "")),
                "type": "invoice",
                "summary": f"Invoice: {inv.get('service', '?')} — \u00a3{total:.2f} — {inv.get('status', 'Draft')}",
                "status": inv.get("status", ""),
                "id": inv.get("id", ""),
            })

    # Sessions
    for s in list_records("sessions"):
        if needle in str(s.get("client", "")).lower():
            events.append({
                "date": f"{s.get('date', '')} {s.get('time', '')}",
                "type": "session",
                "summary": f"Session: {s.get('service', 'Session')} ({s.get('duration', '?')}) — {s.get('status', 'Scheduled')}",
                "status": s.get("status", ""),
                "id": s.get("id", ""),
            })

    # Drafts
    for d in list_records("drafts"):
        if needle in str(d.get("recipient", "")).lower():
            events.append({
                "date": d.get("created_at", ""),
                "type": "draft",
                "summary": f"Draft: {d.get('type', 'message')} — {d.get('subject', '')[:60]} — {d.get('status', 'Pending')}",
                "status": d.get("status", ""),
                "id": d.get("id", ""),
            })

    # Followups
    for f in list_records("followups"):
        if needle in str(f.get("subject", "")).lower() or needle in str(f.get("notes", "")).lower():
            events.append({
                "date": f.get("due", f.get("created_at", "")),
                "type": "followup",
                "summary": f"Follow-up: {f.get('subject', '')[:60]} — {f.get('status', 'Open')}",
                "status": f.get("status", ""),
                "id": f.get("id", ""),
            })

    # Expenses
    for e in list_records("expenses"):
        if needle in str(e.get("client", "")).lower() or needle in str(e.get("project", "")).lower():
            amount = float(e.get("amount", 0) or 0)
            events.append({
                "date": e.get("date", e.get("created_at", "")),
                "type": "expense",
                "summary": f"Expense: {e.get('category', '?')} — \u00a3{amount:.2f} ({e.get('description', '')[:40]})",
                "status": "",
                "id": e.get("id", ""),
            })

    # Leads
    for lead in list_records("leads"):
        if needle in str(lead.get("lead", "")).lower():
            events.append({
                "date": lead.get("created_at", ""),
                "type": "lead",
                "summary": f"Lead: {lead.get('service_fit', '?')} — Score {lead.get('score', '?')} — {lead.get('status', 'New')}",
                "status": lead.get("status", ""),
                "id": lead.get("id", ""),
            })

    # Mix reviews — matched by title substring since mix_reviews has no
    # dedicated client column; name the client/project in the upload title
    # (e.g. "Sam Artist - Final Mix v3") for this to pick it up.
    try:
        reviews = (list_mix_reviews or _default_list_mix_reviews)()
    except Exception:
        reviews = []
    for r in reviews:
        title = str(r.get("title", ""))
        if needle in title.lower():
            flags = r.get("flags") or []
            flag_note = f", {len(flags)} flag(s)" if flags else ""
            events.append({
                "date": r.get("created_at", ""),
                "type": "mix_review",
                "summary": f"Mix review: {title} — {r.get('status', 'completed')}{flag_note}",
                "status": r.get("status", ""),
                "id": r.get("id", ""),
            })

    # AutoMix jobs — matched via the project(s) already confirmed to belong to
    # this client above (automix_jobs.project_id has no client column of its
    # own, same join shape as the mix-review title match).
    try:
        jobs = (list_automix_jobs or _default_list_automix_jobs)()
    except Exception:
        jobs = []
    for job in jobs:
        if str(job.get("project_id", "")) in client_project_ids:
            events.append({
                "date": job.get("created_at", ""),
                "type": "automix_job",
                "summary": f"AutoMix: {job.get('genre', '?')} mixdown — {job.get('status', '?')}",
                "status": job.get("status", ""),
                "id": job.get("id", ""),
            })

    if date_range:
        events = [e for e in events if _in_range(e.get("date", ""), date_range)]

    # Sort by date descending
    events.sort(key=lambda e: e.get("date", ""), reverse=True)
    return events


def client_timeline(
    list_records: Callable[[str], list[dict]],
    name: str,
    *,
    list_mix_reviews: Callable[[], list[dict]] | None = None,
    list_automix_jobs: Callable[[], list[dict]] | None = None,
    date_range: tuple[str, str] | None = None,
) -> str:
    """Show full timeline for a client, optionally scoped to date_range."""
    events = _make_timeline_events(
        name, list_records, list_mix_reviews=list_mix_reviews,
        list_automix_jobs=list_automix_jobs, date_range=date_range,
    )

    if not events:
        return (
            f"No records found for client: {name} in that time range."
            if date_range else f"No records found for client: {name}"
        )

    # Count by type
    by_type: dict[str, int] = {}
    for e in events:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1

    type_labels = {
        "project": "Projects", "invoice": "Invoices", "session": "Sessions",
        "draft": "Drafts", "followup": "Follow-ups", "expense": "Expenses", "lead": "Leads",
        "mix_review": "Mix reviews", "automix_job": "AutoMix jobs",
    }
    summary_parts = [f"{count} {type_labels.get(t, t)}" for t, count in sorted(by_type.items())]

    lines = [
        f"\U0001f4c4 Client Timeline: {name.title()}",
        f"{'=' * 45}",
        f"  {', '.join(summary_parts)}",
        f"  {len(events)} total interaction(s)",
        "",
    ]

    for event in events:
        date = (event.get("date") or "?")[:10]
        etype = event["type"]
        summary = event["summary"]
        status = event.get("status", "")

        # Emoji per type
        type_emoji = {
            "project": "\U0001f4cb",
            "invoice": "\U0001f4b0",
            "session": "\U0001f3a4",
            "draft": "\u2709\ufe0f",
            "followup": "\U0001f514",
            "expense": "\U0001f4b2",
            "lead": "\U0001f50d",
            "mix_review": "\U0001f3a7",
            "automix_job": "\U0001f39b\ufe0f",
        }.get(etype, "\u2022")

        status_tag = ""
        if status:
            status_lower = status.lower()
            if status_lower in ("paid", "done", "completed", "delivered", "approved", "confirmed"):
                status_tag = " \u2705"
            elif status_lower in ("overdue", "cancelled", "rejected", "not interested"):
                status_tag = " \u26a0\ufe0f"
            else:
                status_tag = f" [{status}]"

        lines.append(f"  {date} {type_emoji} {summary}{status_tag}")

    return "\n".join(lines)


def client_summary(
    list_records: Callable[[str], list[dict]],
    name: str,
    *,
    list_mix_reviews: Callable[[], list[dict]] | None = None,
    list_automix_jobs: Callable[[], list[dict]] | None = None,
    date_range: tuple[str, str] | None = None,
) -> str:
    """Show a compact summary for a client, optionally scoped to date_range."""
    events = _make_timeline_events(
        name, list_records, list_mix_reviews=list_mix_reviews,
        list_automix_jobs=list_automix_jobs, date_range=date_range,
    )

    # Latest project
    projects = [e for e in events if e["type"] == "project"]
    latest_project = projects[0]["summary"] if projects else "None"

    # Outstanding invoices
    invoices = [e for e in events if e["type"] == "invoice"]
    unpaid = [e for e in invoices if e.get("status", "").lower() in ("draft", "sent", "overdue")]
    unpaid_total = 0.0
    for e in unpaid:
        m = __import__("re").search(r"\u00a3([\d.]+)", e["summary"])
        if m:
            unpaid_total += float(m.group(1))

    # Upcoming sessions
    sessions = [e for e in events if e["type"] == "session" and e.get("status", "").lower() not in ("done", "cancelled")]

    # Open followups
    followups = [e for e in events if e["type"] == "followup" and e.get("status", "").lower() == "open"]

    # Latest mix review \u2014 this is the cross-domain link: a client summary
    # now surfaces their mix's technical status, not just business records.
    reviews = [e for e in events if e["type"] == "mix_review"]
    latest_review_line = f"  Latest mix review: {reviews[0]['summary'].replace('Mix review: ', '', 1)}\n" if reviews else ""

    # Latest AutoMix job \u2014 same cross-domain pattern (audit fix Stage 3,
    # docs/AUDIT_FIX_EXECUTION_PLAN_2026-07-08.md): a client summary now
    # surfaces their mixdown job status too, not just business + mix review.
    jobs = [e for e in events if e["type"] == "automix_job"]
    latest_job_line = f"  Latest AutoMix job: {jobs[0]['summary'].replace('AutoMix: ', '', 1)}\n" if jobs else ""

    return (
        f"Client: {name.title()}\n"
        f"{'=' * 30}\n"
        f"  Latest project: {latest_project}\n"
        f"  Outstanding: \u00a3{unpaid_total:.2f} ({len(unpaid)} invoice(s))\n"
        f"  Upcoming sessions: {len(sessions)}\n"
        f"  Open follow-ups: {len(followups)}\n"
        f"{latest_review_line}"
        f"{latest_job_line}"
        f"  Total interactions: {len(events)}"
    )
