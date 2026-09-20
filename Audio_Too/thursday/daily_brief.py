"""Daily Brief composer — one "what's happening today?" artifact.

Assembles the existing Thursday services into a single structured brief:

- Business status   (`thursday.client.business_status`)
- Today's agenda    (`thursday.scheduling.agenda_for_day`)
- Week ahead        (`thursday.scheduling.agenda_for_week`)
- Agent receipts    (`thursday.action_receipts.recent_receipts`)
- Scheduler outlook (`thursday.scheduler.load_schedules` / `should_run`)

Every source degrades gracefully: if a source raises or is missing, its
section is marked ``unavailable`` with the error recorded — the brief never
crashes because one source failed. Rendering produces plain text/markdown.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any, Callable

from thursday import action_receipts, client, scheduler, scheduling

logger = logging.getLogger(__name__)

BRIEF_SECTIONS = (
    "business_status",
    "company_state",
    "agenda",
    "week_ahead",
    "agent_receipts",
    "scheduler",
)


def _section_ok(payload: Any) -> dict[str, Any]:
    return {"status": "ok", "payload": payload}


def _section_unavailable(error: Exception) -> dict[str, Any]:
    logger.warning("daily brief section unavailable: %s", error)
    return {"status": "unavailable", "error": str(error)}


def _gather(name: str, fn: Callable[[], Any]) -> dict[str, Any]:
    """Run one source, fail closed per-section."""
    try:
        payload = fn()
        if payload is None:
            raise ValueError(f"{name}: source returned nothing")
        return _section_ok(payload)
    except Exception as exc:  # noqa: BLE001 — degrade, never propagate
        return _section_unavailable(exc)


# ─── Source adapters ─────────────────────────────────────────────────────


def _business_status_source() -> str:
    from thursday import status_cache

    text, age = status_cache.get_business_status(ttl_seconds=600)
    stripped = text.strip()
    if not stripped:
        raise ValueError("business status returned an empty report")
    note = status_cache.age_note(age)
    return f"{stripped}\n_{note}_" if note else stripped


def _agenda_source(today: date) -> str:
    return scheduling.agenda_for_day(today).strip()


def _week_ahead_source(today: date) -> str:
    return scheduling.agenda_for_week(today.isoformat()).strip()


def _agent_receipts_source(now: datetime) -> list[dict[str, Any]]:
    cutoff = now - timedelta(hours=24)
    receipts = action_receipts.recent_receipts(since=cutoff.timestamp(), limit=20)
    return [
        {
            "receipt_id": r.receipt_id,
            "service_id": r.service_id,
            "status": r.status,
            "created_at": r.created_at,
        }
        for r in receipts
    ]


def _scheduler_source() -> dict[str, Any]:
    schedules = scheduler.load_schedules()
    due_now: list[str] = []
    now_dt = datetime.now()
    for cadence in ("daily", "weekly", "monthly"):
        for task in schedules.get(cadence, []) or []:
            name = str(task.get("name") or task.get("task") or "?")
            try:
                if scheduler.should_run(task):
                    due_now.append(f"{cadence}/{name}")
            except Exception as exc:  # noqa: BLE001 — per-task degrade
                logger.warning("scheduler check failed for %s: %s", name, exc)
    counts = {
        cadence: len(schedules.get(cadence, []) or [])
        for cadence in ("daily", "weekly", "monthly")
    }
    return {"registered": counts, "due_now": sorted(due_now)}


def _company_state_source() -> str:
    """Render the structured company-state section from nite_ai contracts.

    Bounded, prioritised, freshness-honest: blockers → overdue → due today
    → approvals → failed agents → at-risk goals. Empty state says so.
    """
    from thursday import company_state

    snapshot = company_state.get_snapshot()
    lines: list[str] = []

    if snapshot.is_empty():
        lines.append("_No company state recorded yet._")
        return "\n".join(lines)

    if snapshot.blocked_tasks:
        lines.append("**Blocked:**")
        for t in snapshot.blocked_tasks:
            waiting = f" (waiting on {', '.join(t.blocked_by)})" if t.blocked_by else ""
            lines.append(f"- {t.title} — {t.project_id}{waiting}")
    if snapshot.overdue_tasks:
        lines.append("**Overdue:**")
        for t in snapshot.overdue_tasks:
            lines.append(f"- {t.title} — {t.project_id} (P{t.priority})")
    if snapshot.due_today_tasks:
        lines.append("**Due today:**")
        for t in snapshot.due_today_tasks:
            lines.append(f"- {t.title} — {t.project_id} (P{t.priority})")
    if snapshot.pending_approvals:
        lines.append("**Needs your approval:**")
        for a in snapshot.pending_approvals:
            lines.append(f"- {a.summary} [{a.approval_id}] ({a.action_level} risk)")
    if snapshot.failed_agent_runs:
        lines.append("**Agent failures:**")
        for r in snapshot.failed_agent_runs:
            why = f" — {r.blocker}" if r.blocker else ""
            lines.append(f"- {r.agent_id}{why}")
    at_risk = [
        g
        for g in snapshot.goals
        if g.target_date_epoch is not None
        and g.target_date_epoch < snapshot.captured_at_epoch
        and g.progress < 1.0
    ]
    if at_risk:
        lines.append("**Goals past target date:**")
        for g in at_risk:
            lines.append(f"- {g.title} ({int(g.progress * 100)}% complete)")

    note = snapshot.freshness_note()
    if note and len(lines) > 0:
        lines.append(f"\n_{note}_")

    return "\n".join(lines) if lines else "_No company state recorded yet._"


# ─── Composer ────────────────────────────────────────────────────────────


def compose_daily_brief(*, today: date | None = None) -> dict[str, Any]:
    """Compose the full daily brief as a structured dict.

    Args:
        today: The brief's reference day (defaults to today).

    Returns:
        Dict with ``generated_at``, ``today``, per-section dicts under
        ``sections`` and a short ``summary`` line count of availability.
    """
    ref_day = today or date.today()
    now = datetime.now()

    # Sources are independent reads (subprocess, JSON, SQLite) and can be
    # slow in different ways — compose them concurrently so the brief's
    # latency tracks the slowest source, not the sum of all of them.
    jobs: dict[str, Callable[[], dict[str, Any]]] = {
        "business_status": lambda: _gather(
            "business_status", lambda: _business_status_source()
        ),
        "company_state": lambda: _gather("company_state", _company_state_source),
        "agenda": lambda: _gather("agenda", lambda: _agenda_source(ref_day)),
        "week_ahead": lambda: _gather(
            "week_ahead", lambda: _week_ahead_source(ref_day)
        ),
        "agent_receipts": lambda: _gather(
            "agent_receipts", lambda: _agent_receipts_source(now)
        ),
        "scheduler": lambda: _gather("scheduler", _scheduler_source),
    }
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {name: pool.submit(fn) for name, fn in jobs.items()}
        sections = {name: fut.result() for name, fut in futures.items()}

    available = [n for n, s in sections.items() if s["status"] == "ok"]
    unavailable = [n for n, s in sections.items() if s["status"] != "ok"]

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "today": ref_day.isoformat(),
        "sections": sections,
        "summary": {
            "available": available,
            "unavailable": unavailable,
            "total_sections": len(sections),
        },
    }


# ─── Rendering ───────────────────────────────────────────────────────────


def render_daily_brief(brief: dict[str, Any]) -> str:
    """Render a composed brief as readable markdown text."""
    lines = [
        f"# Daily Brief — {brief['today']}",
        f"_Generated {brief['generated_at']}_",
        "",
    ]
    sections = brief["sections"]

    # Business status
    biz = sections["business_status"]
    lines.append("## Business Status")
    lines.append(biz["payload"] if biz["status"] == "ok"
                 else "_unavailable_")
    lines.append("")

    # Company state (structured, bounded, freshness-labelled)
    company = sections.get("company_state")
    if company is not None:
        lines.append("## Company State")
        lines.append(company["payload"] if company["status"] == "ok"
                     else "_unavailable_")
        lines.append("")

    # Agenda
    agenda = sections["agenda"]
    lines.append("## Today")
    lines.append(agenda["payload"] if agenda["status"] == "ok"
                 else "_unavailable_")
    lines.append("")

    # Week ahead
    week = sections["week_ahead"]
    lines.append("## Week Ahead")
    lines.append(week["payload"] if week["status"] == "ok"
                 else "_unavailable_")
    lines.append("")

    # Agent receipts
    receipts = sections["agent_receipts"]
    lines.append("## Agent Activity (last 24h)")
    if receipts["status"] == "ok":
        items = receipts["payload"]
        if items:
            for r in items:
                lines.append(
                    f"- `{r['receipt_id']}` {r['service_id']} — {r['status']}"
                )
        else:
            lines.append("_No agent actions in the last 24 hours._")
    else:
        lines.append("_unavailable_")
    lines.append("")

    # Scheduler
    sched = sections["scheduler"]
    lines.append("## Scheduled Tasks")
    if sched["status"] == "ok":
        registered = sched["payload"]["registered"]
        total = sum(registered.values())
        if total == 0:
            lines.append("_No scheduled tasks registered._")
        else:
            counts = ", ".join(
                f"{cadence}: {count}" for cadence, count in registered.items()
            )
            lines.append(f"- Registered — {counts}")
            due = sched["payload"]["due_now"]
            if due:
                lines.append("- Due now: " + ", ".join(due))
            else:
                lines.append("- Nothing due right now.")
    else:
        lines.append("_unavailable_")
    lines.append("")

    summary = brief["summary"]
    if summary["unavailable"]:
        lines.append(
            "> Sections unavailable: " + ", ".join(summary["unavailable"])
        )

    return "\n".join(lines)


def build_daily_brief(
    *,
    today: date | None = None,
    conversational: bool = False,
    user_name: str = "",
) -> tuple[dict[str, Any], str]:
    """Compose and render in one call. Returns ``(brief_dict, text)``.

    ``conversational=True`` adds the legacy briefing's human framing —
    time-based greeting, date line, pending alerts and a closing line — so
    every Thursday surface can consume the ONE canonical composer without
    losing the legacy morning-brief semantics.
    """
    brief = compose_daily_brief(today=today)
    text = render_daily_brief(brief)
    if not conversational:
        return brief, text

    now = datetime.now()
    hour = now.hour
    name_part = f", {user_name}" if user_name else ""
    if hour < 12:
        greeting = f"Good morning{name_part}."
    elif hour < 17:
        greeting = f"Good afternoon{name_part}."
    else:
        greeting = f"Good evening{name_part}."

    lines = [greeting, "", f"Today is {now.strftime('%A, %d %B %Y')}.", ""]

    try:
        from thursday.monitor import get_pending_alerts

        alerts = get_pending_alerts()
        if alerts:
            lines.append(f"You have {len(alerts)} pending alert(s):")
            for alert in alerts[:3]:
                lines.append(f"  - {alert.get('message', '')}")
            lines.append("")
    except ImportError:
        pass

    lines.append(text)
    lines.append("")
    lines.append("Ready when you are.")
    return brief, "\n".join(lines)


# ─── Speakable rendering ─────────────────────────────────────────────────


def _payload_count(payload: str, marker: str) -> int:
    """Count list items under a '**Marker:**' section in a rendered payload."""
    token = f"**{marker}:**"
    if token not in payload:
        return 0
    tail = payload.split(token, 1)[1]
    chunk = tail.split("**", 1)[0]
    count = chunk.count("\n- ")
    if count == 0 and chunk.strip().startswith("- "):
        count = 1
    return count


def render_speakable_brief(brief: dict[str, Any]) -> str:
    """Render the composed brief as speech — no markdown, no IDs, no tables.

    One factual source, three renderers: visual (markdown), conversational
    (framed markdown), speakable (this). Critical facts survive compression;
    quiet days stay short.
    """
    sections = brief["sections"]
    sentences: list[str] = []

    company = sections.get("company_state")
    if company is not None and company["status"] == "ok":
        payload_text = str(company["payload"])
        if "No company state recorded yet" in payload_text:
            pass
        elif "unavailable" in payload_text.lower() and len(payload_text) < 200:
            sentences.append("Company state is unavailable right now.")
        else:
            blocked_n = _payload_count(payload_text, "Blocked")
            overdue_n = _payload_count(payload_text, "Overdue")
            approval_n = _payload_count(payload_text, "Needs your approval")
            failed_n = _payload_count(payload_text, "Agent failures")

            if blocked_n:
                sentences.append(
                    f"You have {blocked_n} blocked "
                    f"{'task' if blocked_n == 1 else 'tasks'} needing attention."
                )
            if overdue_n:
                sentences.append(
                    f"{overdue_n} {'task is' if overdue_n == 1 else 'tasks are'} overdue."
                )
            if approval_n:
                sentences.append(
                    f"{approval_n} {'item needs' if approval_n == 1 else 'items need'} your approval."
                )
            if failed_n:
                sentences.append(
                    "An agent failed. Details are on screen."
                    if failed_n == 1 else
                    f"{failed_n} agents failed. Details are on screen."
                )
            if "STALE" in payload_text:
                sentences.append(
                    "That company data is stale, so treat it as a rough guide."
                )

    agenda = sections["agenda"]
    if agenda["status"] == "ok":
        agenda_text = str(agenda["payload"])
        if "No reminders" not in agenda_text:
            first_line = next(
                (ln for ln in agenda_text.splitlines() if ln.strip()), ""
            )
            if first_line and not first_line.startswith("#"):
                sentences.append(f"On today's agenda: {first_line.strip()}")

    receipts_sec = sections["agent_receipts"]
    if receipts_sec["status"] == "ok":
        items = receipts_sec["payload"]
        completed = sum(1 for r in items if r.get("status") == "completed")
        if completed:
            sentences.append(
                f"{completed} agent action{'' if completed == 1 else 's'} "
                "completed in the last day."
            )

    scheduler = sections["scheduler"]
    if scheduler["status"] == "ok":
        due_now = scheduler["payload"].get("due_now") or []
        if due_now:
            sentences.append(
                f"{len(due_now)} scheduled task{'' if len(due_now) == 1 else 's'} "
                "due right now."
            )

    if not sentences:
        return "All clear. Nothing needs your attention right now."

    lead = "Here's where we stand." if len(sentences) > 1 else ""
    return " ".join(filter(None, [lead] + sentences))
