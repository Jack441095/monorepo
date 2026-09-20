"""Monthly and ad-hoc business reports for Audio_Too.

Pulls data from all tables and generates human-readable summaries.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable


def today() -> date:
    return date.today()


def this_month_start() -> date:
    return today().replace(day=1)


def last_month_start() -> date:
    prev = this_month_start() - timedelta(days=1)
    return prev.replace(day=1)


def last_month_end() -> date:
    return this_month_start() - timedelta(days=1)


def parse_date(value: object) -> date | None:
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        parts = text.split("-")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def str_date(d: date) -> str:
    return d.isoformat()


def monthly_report(list_records: Callable[[str], list[dict]]) -> str:
    """Generate a full monthly business report."""
    month_start = this_month_start()
    prev_month_start = last_month_start()
    prev_month_end = last_month_end()

    clients = list_records("clients")
    projects = list_records("projects")
    invoices = list_records("invoices")
    leads = list_records("leads")
    campaigns = list_records("campaigns")

    # --- Clients ---
    total_clients = len(clients)
    new_clients_this_month = 0
    new_clients_last_month = 0
    for c in clients:
        created = parse_date(c.get("created_at"))
        if created:
            if created >= month_start:
                new_clients_this_month += 1
            elif prev_month_start <= created <= prev_month_end:
                new_clients_last_month += 1

    # --- Projects ---
    total_projects = len(projects)
    new_projects_this_month = 0
    completed_this_month = 0
    active_now = 0
    for p in projects:
        status = (p.get("status") or "Open").lower()
        if status not in {"closed", "complete", "completed", "done"}:
            active_now += 1
        created = parse_date(p.get("created_at"))
        if created and created >= month_start:
            new_projects_this_month += 1
        if status in {"closed", "complete", "completed", "done"}:
            updated = parse_date(p.get("updated_at"))
            if updated and updated >= month_start:
                completed_this_month += 1

    # --- Invoices ---
    total_invoices = len(invoices)
    draft_count = sent_count = paid_count = 0
    this_month_sent = 0
    this_month_paid = 0
    this_month_revenue = 0.0
    last_month_revenue = 0.0
    for inv in invoices:
        status = (inv.get("status") or "").lower()
        if status == "draft":
            draft_count += 1
        elif status == "sent":
            sent_count += 1
        elif status == "paid":
            paid_count += 1

        created = parse_date(inv.get("created_at"))
        total = float(inv.get("total") or 0)
        if created:
            if created >= month_start:
                this_month_sent += 1
                if status == "paid":
                    this_month_revenue += total
                    this_month_paid += 1
            elif prev_month_start <= created <= prev_month_end:
                if status == "paid":
                    last_month_revenue += total

    # --- Leads ---
    total_leads = len(leads)
    new_leads_this_month = 0
    leads_by_source: dict[str, int] = {}
    active_lead_statuses: dict[str, int] = {}
    for lead in leads:
        status = (lead.get("status") or "New").lower()
        source = (lead.get("source") or "unknown").strip()
        if source:
            leads_by_source[source] = leads_by_source.get(source, 0) + 1
        active_lead_statuses[status] = active_lead_statuses.get(status, 0) + 1
        created = parse_date(lead.get("created_at"))
        if created and created >= month_start:
            new_leads_this_month += 1

    # --- Campaigns ---
    active_campaigns = [c for c in campaigns if (c.get("status") or "").lower() not in {"closed", "completed", "ended"}]

    # --- Service demand ---
    service_counts: dict[str, int] = {}
    service_revenue: dict[str, float] = {}
    for p in projects:
        svc = p.get("service") or "General"
        service_counts[svc] = service_counts.get(svc, 0) + 1
    for inv in invoices:
        svc = inv.get("service") or "General"
        status = (inv.get("status") or "").lower()
        total = float(inv.get("total") or 0)
        if status == "paid":
            service_revenue[svc] = service_revenue.get(svc, 0) + total

    top_services = sorted(service_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    month_name = month_start.strftime("%B %Y")
    prev_month_name = prev_month_start.strftime("%B %Y")

    lines = [
        f"\U0001f4ca Monthly Report — {month_name}",
        "=" * 40,
        "",
        "Clients:",
        f"  Total: {total_clients}",
        f"  New this month: {new_clients_this_month}",
        f"  New last month: {new_clients_last_month}",
        "",
        "Projects:",
        f"  Total: {total_projects}",
        f"  Active: {active_now}",
        f"  New this month: {new_projects_this_month}",
        f"  Completed this month: {completed_this_month}",
        "",
        "Invoices & Revenue:",
        f"  Total invoices: {total_invoices}",
        f"  Draft: {draft_count} | Sent: {sent_count} | Paid: {paid_count}",
        f"  Revenue this month ({month_name}): \u00a3{this_month_revenue:.2f}",
        f"  Revenue last month ({prev_month_name}): \u00a3{last_month_revenue:.2f}",
    ]

    if this_month_revenue > 0 or last_month_revenue > 0:
        if last_month_revenue > 0:
            change = ((this_month_revenue - last_month_revenue) / last_month_revenue) * 100
            emoji = "\U0001f4c8" if change > 0 else "\U0001f4c9" if change < 0 else "\u27a1\ufe0f"
            lines.append(f"  {emoji} Month-over-month: {change:+.1f}%")
        else:
            lines.append("  \U0001f4c8 First month with revenue recorded")

    lines.extend([
        "",
        "Leads:",
        f"  Total: {total_leads}",
        f"  New this month: {new_leads_this_month}",
        f"  By status: {dict(active_lead_statuses)}",
    ])

    if leads_by_source:
        lines.append("  By source:")
        for src, count in sorted(leads_by_source.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"    - {src}: {count}")

    lines.extend([
        "",
        "Campaigns:",
        f"  Active: {len(active_campaigns)}",
        f"  Total: {len(campaigns)}",
    ])

    if top_services:
        lines.extend([
            "",
            "Top Services by Demand:",
        ])
        for i, (svc, count) in enumerate(top_services, 1):
            rev = service_revenue.get(svc, 0)
            rev_str = f" | \u00a3{rev:.2f} revenue" if rev > 0 else ""
            lines.append(f"  {i}. {svc}: {count} project{'s' if count > 1 else ''}{rev_str}")

    return "\n".join(lines)


def lead_source_report(list_records: Callable[[str], list[dict]]) -> str:
    """Break down leads by source with conversion rates."""
    leads = list_records("leads")
    clients = list_records("clients")

    source_data: dict[str, dict] = {}
    for lead in leads:
        source = (lead.get("source") or "unknown").strip()
        if source not in source_data:
            source_data[source] = {"total": 0, "closed": 0, "not_interested": 0, "warm": 0, "hot": 0}
        source_data[source]["total"] += 1
        status = (lead.get("status") or "New").lower()
        if status == "closed":
            source_data[source]["closed"] += 1
        elif status == "not interested":
            source_data[source]["not_interested"] += 1
        elif status == "warm":
            source_data[source]["warm"] += 1
        elif status == "hot":
            source_data[source]["hot"] += 1

    client_names = {c.get("name", "").lower() for c in clients}
    for s in source_data:
        converted = sum(
            1 for lead in leads
            if (lead.get("source") or "unknown").strip() == s
            and lead.get("lead", "").lower() in client_names
        )
        source_data[s]["converted"] = converted

    lines = ["\U0001f50d Lead Sources Report", "=" * 30, ""]
    if not source_data:
        lines.append("No leads recorded yet.")
        return "\n".join(lines)

    lines.append(f"{'Source':<20} {'Total':>6} {'Warm':>6} {'Hot':>6} {'Conv.':>6} {'Rate':>8}")
    lines.append("-" * 60)
    for source, data in sorted(source_data.items(), key=lambda x: x[1]["total"], reverse=True):
        total = data["total"]
        warm = data["warm"]
        hot = data["hot"]
        converted = data.get("converted", 0)
        rate = (converted / total * 100) if total > 0 else 0
        lines.append(f"{source:<20} {total:>6} {warm:>6} {hot:>6} {converted:>6} {rate:>7.0f}%")

    return "\n".join(lines)


def service_demand_report(list_records: Callable[[str], list[dict]]) -> str:
    """Show most requested services with project counts and revenue."""
    projects = list_records("projects")
    invoices = list_records("invoices")
    leads = list_records("leads")

    project_counts: dict[str, int] = {}
    lead_counts: dict[str, int] = {}
    revenue_by_service: dict[str, float] = {}

    for p in projects:
        svc = p.get("service") or "General"
        project_counts[svc] = project_counts.get(svc, 0) + 1

    for lead in leads:
        svc = lead.get("service_fit") or "General"
        lead_counts[svc] = lead_counts.get(svc, 0) + 1

    for inv in invoices:
        svc = inv.get("service") or "General"
        status = (inv.get("status") or "").lower()
        total = float(inv.get("total") or 0)
        if status == "paid":
            revenue_by_service[svc] = revenue_by_service.get(svc, 0) + total

    all_services = set(list(project_counts.keys()) + list(lead_counts.keys()) + list(revenue_by_service.keys()))
    lines = ["\U0001f4ca Service Demand Report", "=" * 35, ""]

    if not all_services:
        lines.append("No services recorded yet.")
        return "\n".join(lines)

    sorted_services = sorted(
        all_services,
        key=lambda s: project_counts.get(s, 0) + lead_counts.get(s, 0),
        reverse=True,
    )

    lines.append(f"{'Service':<20} {'Projects':>9} {'Leads':>7} {'Revenue':>10}")
    lines.append("-" * 55)
    for svc in sorted_services:
        pc = project_counts.get(svc, 0)
        lc = lead_counts.get(svc, 0)
        rev = revenue_by_service.get(svc, 0)
        rev_str = f"\u00a3{rev:.2f}" if rev > 0 else "-"
        lines.append(f"{svc:<20} {pc:>9} {lc:>7} {rev_str:>10}")

    return "\n".join(lines)


def invoice_aging_report(list_records: Callable[[str], list[dict]]) -> str:
    """Show overdue/unpaid invoices sorted by age."""
    invoices = list_records("invoices")
    today_d = today()

    unpaid = []
    for inv in invoices:
        status = (inv.get("status") or "").lower()
        if status in {"paid", "draft"}:
            continue
        total = float(inv.get("total") or 0)
        created = parse_date(inv.get("created_at"))
        days_since = (today_d - created).days if created else 0
        unpaid.append({
            "id": inv.get("id", ""),
            "client": inv.get("client", "Unknown"),
            "service": inv.get("service", ""),
            "total": total,
            "status": inv.get("status", ""),
            "date": inv.get("created_at", "")[:10],
            "days": days_since,
        })

    unpaid.sort(key=lambda r: r["days"], reverse=True)

    lines = ["\U0001f4b5 Invoice Aging Report", "=" * 40, ""]
    if not unpaid:
        lines.append("No overdue or unpaid invoices.")
        return "\n".join(lines)

    lines.append(f"{'ID':<10} {'Client':<20} {'Total':>8} {'Status':>8} {'Age (days)':>10}")
    lines.append("-" * 65)
    for inv in unpaid:
        lines.append(
            f"{inv['id']:<10} {inv['client']:<20} \u00a3{inv['total']:>6.2f} {inv['status']:>8} {inv['days']:>10}"
        )

    total_unpaid = sum(i["total"] for i in unpaid)
    lines.append("-" * 65)
    lines.append(f"{'Total':<30} \u00a3{total_unpaid:>6.2f} {'':>8} {len(unpaid):>10}")

    return "\n".join(lines)


def week_ahead_report(list_records: Callable[[str], list[dict]]) -> str:
    """Show everything due in the next 7 days."""
    today_d = today()
    next_week = today_d + timedelta(days=7)

    items: list[dict] = []

    # Projects with deadlines or follow-ups this week
    for p in list_records("projects"):
        status = (p.get("status") or "Open").lower()
        if status in {"closed", "complete", "completed", "done"}:
            continue
        for field, label in [("deadline", "Deadline"), ("follow_up", "Follow-up")]:
            val = p.get(field, "")
            d = parse_date(val)
            if d and today_d <= d <= next_week:
                items.append({
                    "type": "project",
                    "name": f"{p.get('client')}/{p.get('project')}",
                    "detail": f"{label}: {p.get('waiting_on') or 'unspecified'}",
                    "date": val,
                })

    # Leads with follow-ups this week
    for lead in list_records("leads"):
        status = (lead.get("status") or "New").lower()
        if status in {"closed", "not interested"}:
            continue
        val = lead.get("follow_up", "")
        d = parse_date(val)
        if d and today_d <= d <= next_week:
            items.append({
                "type": "lead",
                "name": lead.get("lead", "Unknown"),
                "detail": f"Follow-up: {lead.get('next_action') or 'Check in'}",
                "date": val,
            })

    # Followups due this week
    for f in list_records("followups"):
        status = (f.get("status") or "Open").lower()
        if status in {"done", "closed", "complete", "completed"}:
            continue
        val = f.get("due", "")
        d = parse_date(val)
        if d and today_d <= d <= next_week:
            items.append({
                "type": "followup",
                "name": f.get("subject", "Untitled"),
                "detail": f.get("notes", ""),
                "date": val,
            })

    items.sort(key=lambda r: r.get("date", ""))

    lines = ["\U0001f4c5 Week Ahead — Next 7 Days", "=" * 40, ""]
    if not items:
        lines.append("Nothing due in the next 7 days.")
        return "\n".join(lines)

    for item in items:
        lines.append(f"  [{item['type']}] {item['name']} — {item['detail']} ({item['date']})")

    lines.append(f"\nTotal: {len(items)} item{'s' if len(items) > 1 else ''}")
    return "\n".join(lines)
