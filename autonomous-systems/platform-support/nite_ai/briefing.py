"""Deterministic company brief assembly (Phases 6C/6D).

Builds DailyBriefData / WeeklyReviewData from persisted structured company
state. Priority selection is fully deterministic and inspectable — an LLM may
later phrase the output but never chooses priorities.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from nite_ai.company_store import CompanyStore
from nite_ai.domain import DailyBriefData, GoalKind, ItemStatus, WeeklyReviewData
from nite_ai.errors import ValidationError


def _iso_date(epoch: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(epoch))


def _start_of_week(epoch: float) -> float:
    t = time.gmtime(epoch)
    weekday = t.tm_wday  # Monday=0
    midnight = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, 0))
    return midnight - weekday * 86400


def assemble_daily_brief(
    store: CompanyStore, *, now_epoch: float | None = None
) -> DailyBriefData:
    """Deterministic daily brief from structured state.

    Priority rule (inspectable, fixed):
      1. blocked tasks (blockers surfaced separately)
      2. overdue tasks (due < now), highest priority value first
      3. due-today tasks, highest priority value first
      4. active high-priority backlog (priority >= 5)
    """
    now = now_epoch if now_epoch is not None else time.time()
    today = _iso_date(now)
    day_start = time.mktime(time.strptime(today, "%Y-%m-%d"))
    day_end = day_start + 86400

    active_tasks = store.list_tasks(status=ItemStatus.ACTIVE)
    blocked = store.list_tasks(status=ItemStatus.BLOCKED)
    goals = store.list_goals(status=ItemStatus.ACTIVE)

    overdue = [t for t in active_tasks if t.due_epoch is not None and t.due_epoch < now]
    due_today = [
        t for t in active_tasks
        if t.due_epoch is not None and day_start <= t.due_epoch < day_end
    ]
    high_priority = [t for t in active_tasks if t.priority >= 5 and t.due_epoch is None]

    overdue.sort(key=lambda t: (-t.priority, t.due_epoch or 0))
    due_today.sort(key=lambda t: (-t.priority, t.due_epoch or 0))
    high_priority.sort(key=lambda t: -t.priority)

    priorities = (
        [t.task_id for t in overdue]
        + [t.task_id for t in due_today]
        + [t.task_id for t in high_priority]
    )[:10]

    runs = store.recent_agent_runs(limit=10)
    completions = sorted(
        {r["agent_id"] for r in runs if r["status"] == "completed"}
    )
    goals_at_risk = sorted(
        g.goal_id for g in goals
        if g.target_date_epoch is not None and g.target_date_epoch < now
        and g.progress < 1.0
    )

    return DailyBriefData(
        brief_date=today,
        top_priorities=priorities,
        due_today=[t.task_id for t in due_today],
        blockers=[t.task_id for t in blocked],
        agent_completions=completions,
        goals_at_risk=goals_at_risk,
    )


def assemble_weekly_review(
    store: CompanyStore, *, now_epoch: float | None = None
) -> WeeklyReviewData:
    now = now_epoch if now_epoch is not None else time.time()
    week_start = _start_of_week(now)
    week_label = time.strftime("%G-W%V", time.gmtime(now))

    goals = store.list_goals()
    active_tasks = store.list_tasks()
    completed = [t for t in active_tasks if t.status is ItemStatus.DONE]
    slipped = [
        t for t in active_tasks
        if t.status in (ItemStatus.ACTIVE, ItemStatus.BLOCKED)
        and t.due_epoch is not None and t.due_epoch < week_start
    ]
    runs = store.recent_agent_runs(limit=50)
    week_runs = [r for r in runs if (r["started_at_epoch"] or 0) >= week_start]

    return WeeklyReviewData(
        week_label=week_label,
        goals_progress=tuple(
            (g.goal_id, round(g.progress, 3)) for g in goals if g.status is ItemStatus.ACTIVE
        ),
        completed_task_ids=tuple(t.task_id for t in completed),
        slipped_item_ids=tuple(sorted(t.task_id for t in slipped)),
        decisions_made=tuple(
            d["decision_id"] for d in store.list_open_decisions()
        ),
        risks=tuple(r["risk_id"] for r in store.list_active_risks()),
        next_week_priorities=tuple(
            r["task_id"] for r in week_runs if r["status"] == "completed" and r["task_id"]
        )[:10],
    )


__all__ = ["assemble_daily_brief", "assemble_weekly_review"]
