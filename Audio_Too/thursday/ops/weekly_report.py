"""Weekly company report (Thursday Ops upgrade, phase 4 — REPORTING SYSTEM).

Aggregates the real, already-built Ops-upgrade modules into one view
rather than adding a new content-generating layer of its own: task_ledger
(phase 1), macro_analytics + feedback's agent reliability (phase 1/D2.2-
D2.3), marketing_ops + advertising_ops (phase 2), funding_ops (phase 3).
Every number in this report is a pass-through of a call to one of those
modules' own already-evidenced functions -- this module does not compute,
estimate, or invent anything new. If a sub-module has nothing to report,
this report says that plainly rather than omitting the section or
guessing.

Also writes a machine-readable receipt (JSON, one file per report) under
analytics/ -- the spec's "REPORTING SYSTEM" run-receipt idea, adapted
from a per-run receipt to a per-weekly-report one since Thursday doesn't
have a single "autonomous run" boundary the way the spec's Codex-facing
framing assumed.
"""

from __future__ import annotations

import json
from datetime import datetime

from thursday.atomic_io import atomic_write
from thursday.runtime_paths import runtime_dir


def compose_weekly_report() -> dict:
    from thursday import feedback
    from thursday.ops import task_ledger, macro_analytics
    from thursday.ops import marketing_ops, advertising_ops, funding_ops

    active = task_ledger.active_tasks()
    blocked = task_ledger.blocked_tasks()
    needs_approval = task_ledger.tasks_requiring_approval()

    macro_stats = macro_analytics.get_macro_stats()
    reliability = feedback.get_helpfulness_summary()

    marketing_plans = marketing_ops.list_marketing_plans()
    ad_plans = advertising_ops.list_campaign_plans()
    traction = funding_ops.get_live_traction_counts()

    risks = []
    for t in blocked:
        reason = t.blockers[-1] if t.blockers else "no reason recorded"
        risks.append(f"[{t.workstream}] {t.objective} ({t.task_id}) blocked: {reason}")
    if all(isinstance(v, int) and v == 0 for v in traction.values()):
        risks.append("Zero recorded traction (clients/leads/invoices/enquiries) — pre-revenue.")

    if needs_approval:
        next_action = (
            f"Review {len(needs_approval)} item(s) awaiting approval, "
            f"starting with {needs_approval[0].task_id}."
        )
    elif blocked:
        next_action = f"Unblock {blocked[0].task_id}: {blocked[0].objective}"
    elif active:
        by_priority = sorted(active, key=lambda t: {"urgent": 0, "high": 1, "medium": 2, "low": 3}.get(t.priority, 99))
        next_action = by_priority[0].next_action or f"Decide the next step for {by_priority[0].task_id}."
    else:
        next_action = "No open tasks in the ledger — nothing queued to act on this week."

    return {
        "generated_at": datetime.now().isoformat(),
        "tasks": {
            "active_count": len(active),
            "blocked_count": len(blocked),
            "approval_count": len(needs_approval),
            "active": [t.to_dict() for t in active],
            "blocked": [t.to_dict() for t in blocked],
            "needs_approval": [t.to_dict() for t in needs_approval],
        },
        "macro_stats": macro_stats,
        "agent_reliability": reliability,
        "marketing": {
            "plans_on_file": len(marketing_plans),
        },
        "advertising": {
            "plans_on_file": len(ad_plans),
        },
        "funding": {
            "traction": traction,
        },
        "risks": risks,
        "next_action": next_action,
    }


def render_weekly_report(report: dict) -> str:
    t = report["tasks"]
    lines = [
        "WEEKLY COMPANY REPORT",
        f"Generated: {report['generated_at']}",
        "",
        "STATUS:",
        f"  {t['active_count']} active task(s), {t['blocked_count']} blocked, "
        f"{t['approval_count']} awaiting approval.",
        "",
        "TASKS:",
    ]
    if t["active"]:
        for raw in t["active"][:5]:
            lines.append(f"  - [{raw['workstream']}] {raw['objective']} ({raw['task_id']}) — {raw['status']}")
        if len(t["active"]) > 5:
            lines.append(f"  ...and {len(t['active']) - 5} more (see 'active tasks').")
    else:
        lines.append("  No active tasks.")
    lines.append("")

    lines.append("EVIDENCE:")
    mstats = report["macro_stats"]
    if mstats.get("total_executions", 0):
        lines.append(f"  Macro executions recorded: {mstats['total_executions']} (see 'macro stats').")
    else:
        lines.append("  No macro executions recorded this period.")
    reliability = report["agent_reliability"]
    if reliability.get("total_records", 0):
        lines.append(f"  Feedback records: {reliability['total_records']} (see 'agent reliability').")
    else:
        lines.append("  No feedback data collected yet.")
    lines.append(f"  Marketing plans on file: {report['marketing']['plans_on_file']}.")
    lines.append(f"  Advertising plans on file: {report['advertising']['plans_on_file']}.")
    traction = report["funding"]["traction"]
    traction_line = ", ".join(f"{k}: {v}" for k, v in traction.items())
    lines.append(f"  Live traction (app.db): {traction_line}.")
    lines.append("")

    lines.append("RISKS:")
    if report["risks"]:
        for r in report["risks"]:
            lines.append(f"  - {r}")
    else:
        lines.append("  None recorded.")
    lines.append("")

    lines.append("BLOCKERS:")
    if t["blocked"]:
        for raw in t["blocked"]:
            reason = raw["blockers"][-1] if raw["blockers"] else "no reason recorded"
            lines.append(f"  - [{raw['workstream']}] {raw['objective']} ({raw['task_id']}): {reason}")
    else:
        lines.append("  None recorded.")
    lines.append("")

    lines.append("APPROVAL NEEDED:")
    if t["needs_approval"]:
        for raw in t["needs_approval"]:
            lines.append(f"  - [{raw['workstream']}] {raw['objective']} ({raw['task_id']})")
    else:
        lines.append("  None recorded.")
    lines.append("")

    lines.append("NEXT ACTION:")
    lines.append(f"  {report['next_action']}")

    return "\n".join(lines)


def write_receipt(report: dict) -> str:
    """Persist the report as a machine-readable receipt. Returns the
    receipt's file path (as a string) for reference in the rendered text.
    """
    receipts_dir = runtime_dir("analytics", "THURSDAY_ANALYTICS_DIR") / "weekly_reports"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    stamp = report["generated_at"].replace(":", "-")
    path = receipts_dir / f"weekly-report-{stamp}.json"
    try:
        atomic_write(path, json.dumps(report, indent=2))
    except OSError:
        return "(receipt write failed — see logs)"
    return str(path)


def weekly_company_report() -> str:
    report = compose_weekly_report()
    receipt_path = write_receipt(report)
    text = render_weekly_report(report)
    return f"{text}\n\nReceipt saved: {receipt_path}"
