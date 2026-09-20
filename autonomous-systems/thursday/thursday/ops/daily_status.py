"""Founder-facing "where are we today" operations status (Thursday Ops
upgrade, phase 1). Composes thursday.ops.task_ledger's open work on top of the
existing canonical daily_brief (thursday.daily_brief.build_daily_brief) --
it does not re-derive business-health data that already exists, and it
does not invent product/commercial status that has no real data source
wired to it yet.

Anti-hallucination contract (matches thursday.company_state's "labelled
and correct" discipline, and the reorg-plan-wide "never fabricate
evidence" rule): every section here is either (a) read directly from
task_ledger records the founder or Thursday actually created, (b) the
existing daily_brief's own already-evidenced sections, or (c) explicitly
marked "Evidence missing" rather than guessed. In particular: PRODUCT
STATUS and COMMERCIAL STATUS have no real per-product data source
connected yet (no Submit/SLO/KENN status API this module can call), so
those lines say so plainly instead of fabricating a status.
"""

from __future__ import annotations

from datetime import date, datetime

from thursday.ops import task_ledger

_NO_DATA_SOURCE = "Evidence missing — no data source connected yet."

_PRIORITY_ORDER = {"urgent": 0, "high": 1, "medium": 2, "low": 3}


def _sorted_by_priority(records: list[task_ledger.TaskRecord]) -> list[task_ledger.TaskRecord]:
    return sorted(records, key=lambda r: _PRIORITY_ORDER.get(r.priority, 99))


def compose_daily_status(*, today: date | None = None) -> dict:
    """Return the structured status dict; render_daily_status() formats it."""
    today = today or date.today()
    active = _sorted_by_priority(task_ledger.active_tasks())
    blocked = task_ledger.blocked_tasks()
    needs_approval = task_ledger.tasks_requiring_approval()
    top_three = active[:3]

    if top_three:
        recommended_action = top_three[0].next_action or (
            f"Decide the next step for '{top_three[0].objective}' "
            f"({top_three[0].task_id}) — it has no next_action recorded yet."
        )
    else:
        recommended_action = (
            "No active tasks in the ledger. Ask Thursday to create one, "
            "or say \"what should I focus on\" once tasks exist."
        )

    can_prepare = []
    for t in active[:5]:
        if t.status == "proposed":
            can_prepare.append(f"Plan out '{t.objective}' ({t.task_id})")
    if not can_prepare:
        can_prepare = ["Nothing queued to prepare — the active list has no proposed-but-unplanned tasks."]

    return {
        "date": today.isoformat(),
        "top_priorities": top_three,
        "active_count": len(active),
        "blocked": blocked,
        "needs_approval": needs_approval,
        "recommended_action": recommended_action,
        "thursday_can_prepare": can_prepare,
    }


def render_daily_status(status: dict) -> str:
    lines: list[str] = []
    lines.append("NITE DSP DAILY STATUS")
    lines.append("")
    lines.append(f"DATE: {status['date']}")
    lines.append(
        f"OVERALL STATUS: {status['active_count']} active task(s), "
        f"{len(status['blocked'])} blocked, {len(status['needs_approval'])} awaiting approval"
    )
    lines.append("")
    lines.append("TOP 3 PRIORITIES:")
    if status["top_priorities"]:
        for i, t in enumerate(status["top_priorities"], start=1):
            lines.append(f"{i}. [{t.workstream}] {t.objective} ({t.task_id})")
            lines.append(f"   Priority: {t.priority} · Status: {t.status}")
            lines.append(f"   Evidence: {', '.join(t.evidence) if t.evidence else 'none recorded'}")
            lines.append(f"   Next action: {t.next_action or 'not recorded'}")
    else:
        lines.append("  No active tasks in the ledger.")
    lines.append("")

    lines.append("PRODUCT STATUS:")
    for product in ("Submit", "SLO", "KENN", "Thursday"):
        lines.append(f"- {product}: {_NO_DATA_SOURCE}")
    lines.append("")

    lines.append("COMMERCIAL STATUS:")
    for area in ("Website", "Payment/download", "Beta/testers", "Marketing",
                 "Advertising", "Infrastructure", "Funding/investment"):
        lines.append(f"- {area}: {_NO_DATA_SOURCE}")
    lines.append("")

    lines.append("BLOCKERS:")
    if status["blocked"]:
        for t in status["blocked"]:
            reason = t.blockers[-1] if t.blockers else "no reason recorded"
            lines.append(f"- [{t.workstream}] {t.objective} ({t.task_id})")
            lines.append(f"  Blocker: {reason}")
    else:
        lines.append("  None recorded in the ledger.")
    lines.append("")

    lines.append("APPROVALS NEEDED:")
    if status["needs_approval"]:
        for t in status["needs_approval"]:
            lines.append(f"- [{t.workstream}] {t.objective} ({t.task_id}) — status: {t.status}")
    else:
        lines.append("  None recorded in the ledger.")
    lines.append("")

    lines.append("RECOMMENDED FOUNDER ACTION:")
    lines.append(f"  {status['recommended_action']}")
    lines.append("")

    lines.append("THURSDAY CAN PREPARE:")
    for item in status["thursday_can_prepare"]:
        lines.append(f"  - {item}")

    return "\n".join(lines)
