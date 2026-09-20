"""Read-only company-state access for Thursday via nite_ai contracts.

Thursday consumes structured NITE DSP company state (goals, projects,
tasks, risks, decisions, approvals, agent runs) through the platform's
registered company capabilities — never by touching platform internals.

Boundary rules:
- nite_ai is imported lazily; Audio_Too runs without the platform installed;
- the platform never imports this module (inversion of control);
- read-only: this module never writes company state;
- every snapshot carries explicit freshness semantics so stale data can
  never masquerade as real-time truth;
- per-section degradation: one unavailable source never fails the rest.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from thursday.runtime_paths import DATA_DIR

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = DATA_DIR / "company_state.sqlite3"
DB_PATH_ENV = "THURSDAY_COMPANY_DB"

# Freshness classes for a snapshot's age.
CURRENT_MAX_AGE_S = 60.0
RECENT_MAX_AGE_S = 15 * 60.0

# Bounded context selection limits (context budgeting).
MAX_OVERDUE = 8
MAX_BLOCKED = 8
MAX_DUE_TODAY = 8
MAX_RISKS = 6
MAX_DECISIONS = 5
MAX_APPROVALS = 5
MAX_AGENT_RUNS = 10

_CACHE_TTL_S = 30.0


class CompanyStateUnavailable(RuntimeError):
    """Company state cannot be read (platform missing, store unreadable)."""


def _nite_ai():
    import nite_ai  # lazy: Audio_Too runs without the platform installed

    return nite_ai


def _company_modules():
    """Lazily import and return ``(store_mod, domain_mod)`` or raise
    CompanyStateUnavailable when the platform is not installed."""
    try:
        from nite_ai import company_store, domain  # noqa: F401 — submodule load

        return company_store, domain
    except ImportError as exc:
        raise CompanyStateUnavailable(
            f"company state unavailable: nite_ai platform not installed ({exc})"
        ) from exc


def db_path() -> Path:
    configured = os.environ.get(DB_PATH_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_DB_PATH


@dataclass(frozen=True)
class TaskView:
    task_id: str
    title: str
    project_id: str
    status: str
    priority: int
    due_epoch: float | None
    blocked_by: tuple[str, ...]


@dataclass(frozen=True)
class GoalView:
    goal_id: str
    kind: str
    title: str
    status: str
    progress: float
    target_date_epoch: float | None


@dataclass(frozen=True)
class AgentRunView:
    run_id: str
    agent_id: str
    status: str
    blocker: str
    started_at_epoch: float | None
    finished_at_epoch: float | None


@dataclass(frozen=True)
class ApprovalView:
    approval_id: str
    capability_id: str
    summary: str
    action_level: str
    reversibility: str
    created_at_epoch: float


@dataclass(frozen=True)
class CompanySnapshot:
    """Typed, bounded view of current company state with freshness metadata."""

    captured_at_epoch: float
    goals: tuple[GoalView, ...] = ()
    overdue_tasks: tuple[TaskView, ...] = ()
    blocked_tasks: tuple[TaskView, ...] = ()
    due_today_tasks: tuple[TaskView, ...] = ()
    active_projects: tuple[dict[str, Any], ...] = ()
    risks: tuple[dict[str, Any], ...] = ()
    open_decisions: tuple[dict[str, Any], ...] = ()
    pending_approvals: tuple[ApprovalView, ...] = ()
    recent_agent_runs: tuple[AgentRunView, ...] = ()
    failed_agent_runs: tuple[AgentRunView, ...] = ()
    state_note: str = ""

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.captured_at_epoch)

    @property
    def freshness(self) -> str:
        """CURRENT / RECENT / STALE / UNKNOWN classification of this data."""
        if self.captured_at_epoch <= 0:
            return "UNKNOWN"
        age = self.age_seconds
        if age < CURRENT_MAX_AGE_S:
            return "CURRENT"
        if age < RECENT_MAX_AGE_S:
            return "RECENT"
        return "STALE"

    def freshness_note(self) -> str:
        cls = self.freshness
        if cls == "CURRENT":
            return ""
        age_min = int(self.age_seconds // 60)
        if cls == "RECENT":
            return f"(company state from ~{age_min} min ago)"
        if cls == "STALE":
            return (
                f"(company state is STALE — captured {age_min} min ago; "
                "verify before acting)"
            )
        return "(company state availability unknown)"

    def is_empty(self) -> bool:
        return not (
            self.goals
            or self.overdue_tasks
            or self.blocked_tasks
            or self.due_today_tasks
            or self.active_projects
            or self.risks
            or self.open_decisions
            or self.pending_approvals
            or self.recent_agent_runs
        )


# ─── Snapshot construction ───────────────────────────────────────────────


def _task_view(row: Any) -> TaskView:
    return TaskView(
        task_id=str(row.task_id),
        title=str(row.title),
        project_id=str(row.project_id),
        status=str(row.status.value)
        if hasattr(row.status, "value")
        else str(row.status),
        priority=int(row.priority),
        due_epoch=float(row.due_epoch) if row.due_epoch is not None else None,
        blocked_by=tuple(row.blocked_by),
    )


def capture_snapshot(*, now_epoch: float | None = None) -> CompanySnapshot:
    """Read the full bounded company snapshot through the platform store.

    Raises CompanyStateUnavailable when the platform/store cannot be read at
    all; individual entity reads are internally consistent (one SQLite read
    pass), so no partial-section failures exist inside a single snapshot.
    """
    store_mod, domain = _company_modules()

    now = now_epoch if now_epoch is not None else time.time()

    try:
        conn, store = store_mod.open_store(db_path())
    except Exception as exc:  # noqa: BLE001 — degrade honestly
        raise CompanyStateUnavailable(f"company store unavailable: {exc}") from exc

    try:
        item_status = domain.ItemStatus

        goals = [
            GoalView(
                goal_id=g.goal_id,
                kind=str(g.kind.value),
                title=g.title,
                status=str(g.status.value),
                progress=float(g.progress),
                target_date_epoch=float(g.target_date_epoch)
                if g.target_date_epoch is not None
                else None,
            )
            for g in store.list_goals(status=item_status.ACTIVE)
        ]

        projects = [
            {
                "project_id": p.project_id,
                "title": p.title,
                "goal_id": p.goal_id,
                "status": str(p.status.value),
                "progress": float(p.progress),
            }
            for p in store.list_projects()
            if str(p.status.value) == "active"
        ]

        all_tasks = store.list_tasks()
        active = [t for t in all_tasks if t.status is item_status.ACTIVE]
        blocked_rows = [t for t in all_tasks if t.status is item_status.BLOCKED]

        overdue = sorted(
            (t for t in active if t.due_epoch is not None and t.due_epoch < now),
            key=lambda t: (-t.priority, t.due_epoch or 0),
        )[:MAX_OVERDUE]
        # Due-later-today window is disjoint from overdue: [now, local midnight).
        lt = time.localtime(now)
        day_start = time.mktime(
            (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, lt.tm_isdst)
        )
        day_end = day_start + 86400
        due_today = sorted(
            (
                t
                for t in active
                if t.due_epoch is not None and now <= t.due_epoch < day_end
            ),
            key=lambda t: (-t.priority, t.due_epoch or 0),
        )[:MAX_DUE_TODAY]

        blocked = blocked_rows[:MAX_BLOCKED]

        risks = store.list_active_risks()[:MAX_RISKS]
        decisions = store.list_open_decisions()[:MAX_DECISIONS]

        approvals = tuple(
            ApprovalView(
                approval_id=str(a["approval_id"]),
                capability_id=str(a.get("capability_id", "")),
                summary=str(a.get("summary", "")),
                action_level=str(a.get("action_level", "")),
                reversibility=str(a.get("reversibility", "")),
                created_at_epoch=float(a.get("created_at_epoch", 0.0)),
            )
            for a in store.list_pending_approvals()[:MAX_APPROVALS]
        )

        runs_raw = store.recent_agent_runs(limit=MAX_AGENT_RUNS)
        runs = tuple(
            AgentRunView(
                run_id=str(r["run_id"]),
                agent_id=str(r.get("agent_id", "")),
                status=str(r.get("status", "")),
                blocker=str(r.get("blocker", "")),
                started_at_epoch=r.get("started_at_epoch"),
                finished_at_epoch=r.get("finished_at_epoch"),
            )
            for r in runs_raw
        )

        return CompanySnapshot(
            captured_at_epoch=now,
            goals=tuple(goals),
            overdue_tasks=tuple(_task_view(t) for t in overdue),
            blocked_tasks=tuple(_task_view(t) for t in blocked),
            due_today_tasks=tuple(_task_view(t) for t in due_today),
            active_projects=tuple(projects),
            risks=tuple(risks),
            open_decisions=tuple(decisions),
            pending_approvals=approvals,
            recent_agent_runs=runs,
            failed_agent_runs=tuple(r for r in runs if r.status == "failed"),
            state_note="no company state recorded yet" if _snapshot_empty(goals, projects, all_tasks, risks, decisions) else "",
        )
    except CompanyStateUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 — degrade honestly
        raise CompanyStateUnavailable(f"company state read failed: {exc}") from exc
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001 — close best-effort
            pass


def _snapshot_empty(goals, projects, tasks, risks, decisions) -> bool:
    return not (goals or projects or tasks or risks or decisions)


# ─── Cached snapshot access ──────────────────────────────────────────────

_cache_lock = threading.Lock()
_cached: CompanySnapshot | None = None
_cached_at: float = 0.0
_previous: CompanySnapshot | None = None


def get_snapshot(*, force_refresh: bool = False, ttl_seconds: float = _CACHE_TTL_S):
    """Return a cached snapshot within TTL, refreshing on demand/expiry.

    - normal read: cached if younger than ttl_seconds, else refresh;
    - force_refresh=True bypasses the cache;
    - on live-read failure with a cached snapshot present, returns the stale
      snapshot (freshness labelling makes the age explicit to consumers);
    - with no cache and no live source, raises CompanyStateUnavailable.
    """
    global _cached, _cached_at, _previous

    with _cache_lock:
        if not force_refresh and _cached is not None:
            if (time.time() - _cached_at) < ttl_seconds:
                return _cached

    try:
        snapshot = capture_snapshot()
    except CompanyStateUnavailable:
        if _cached is not None:
            logger.warning("company state refresh failed; serving stale snapshot")
            return _cached
        raise

    with _cache_lock:
        _previous = _cached  # keep the superseded snapshot for change diffs
        _cached = snapshot
        _cached_at = time.time()
    return snapshot


def invalidate_cache() -> None:
    """Drop the cached snapshot (next read re-captures)."""
    global _cached, _cached_at
    with _cache_lock:
        _cached = None
        _cached_at = 0.0


# ─── Evidence-typed derivations ──────────────────────────────────────────


def derived_facts(snapshot: CompanySnapshot) -> list[dict[str, Any]]:
    """Deterministic DERIVED facts computed from RETRIEVED snapshot rows.

    Every fact carries its evidence kind and source so callers can never
    present a derivation as a measurement.
    """
    facts: list[dict[str, Any]] = []
    captured = snapshot.captured_at_epoch

    facts.append(
        {
            "name": "overdue_task_count",
            "value": len(snapshot.overdue_tasks),
            "kind": "DERIVED",
            "source": "thursday.company_state",
        }
    )
    facts.append(
        {
            "name": "blocked_task_count",
            "value": len(snapshot.blocked_tasks),
            "kind": "DERIVED",
            "source": "thursday.company_state",
        }
    )
    facts.append(
        {
            "name": "pending_approval_count",
            "value": len(snapshot.pending_approvals),
            "kind": "DERIVED",
            "source": "thursday.company_state",
        }
    )
    facts.append(
        {
            "name": "failed_agent_run_count",
            "value": len(snapshot.failed_agent_runs),
            "kind": "DERIVED",
            "source": "thursday.company_state",
        }
    )

    # Overdue load per active goal (derived join over retrieved rows).
    project_goal: dict[str, str] = {
        p["project_id"]: p["goal_id"] for p in snapshot.active_projects
    }
    per_goal_overdue: dict[str, int] = {}
    for t in snapshot.overdue_tasks:
        goal_id = project_goal.get(t.project_id)
        if goal_id:
            per_goal_overdue[goal_id] = per_goal_overdue.get(goal_id, 0) + 1
    for goal_id, count in sorted(per_goal_overdue.items()):
        facts.append(
            {
                "name": f"goal.{goal_id}.overdue_tasks",
                "value": count,
                "kind": "DERIVED",
                "source": "thursday.company_state",
            }
        )

    # At-risk goals: retrieved rule from the platform brief contract
    # (target date passed while incomplete) — labelled MEASURED-at-source
    # because the platform defines it deterministically.
    at_risk = [
        g.goal_id
        for g in snapshot.goals
        if g.target_date_epoch is not None
        and g.target_date_epoch < captured
        and g.progress < 1.0
    ]
    facts.append(
        {
            "name": "at_risk_goal_ids",
            "value": ",".join(sorted(at_risk)) or "(none)",
            "kind": "MEASURED",
            "source": "nite_ai.briefing.rule",
        }
    )
    return facts


# ─── Change detection (structured state diff) ───────────────────────────


def diff_snapshots(
    previous: CompanySnapshot | None, current: CompanySnapshot
) -> dict[str, list[str]]:
    """Structured diff between two snapshots. All entries are DERIVED facts.

    Categories: blockers_new, blockers_resolved, overdue_new, overdue_cleared,
    approvals_added, agent_failures_new.
    """
    def _ids(tasks) -> set[str]:
        return {t.task_id for t in tasks}

    changes: dict[str, list[str]] = {
        "blockers_new": [],
        "blockers_resolved": [],
        "overdue_new": [],
        "overdue_cleared": [],
        "approvals_added": [],
        "agent_failures_new": [],
    }
    if previous is None:
        return changes

    prev_blockers = _ids(previous.blocked_tasks)
    curr_blockers = _ids(current.blocked_tasks)
    title_by_id = {t.task_id: t.title for t in current.blocked_tasks}
    for tid in sorted(curr_blockers - prev_blockers):
        changes["blockers_new"].append(title_by_id.get(tid, tid))
    prev_blocked_titles = {t.task_id: t.title for t in previous.blocked_tasks}
    for tid in sorted(prev_blockers - curr_blockers):
        changes["blockers_resolved"].append(prev_blocked_titles.get(tid, tid))

    prev_overdue = _ids(previous.overdue_tasks)
    curr_overdue = _ids(current.overdue_tasks)
    overdue_titles = {t.task_id: t.title for t in current.overdue_tasks}
    for tid in sorted(curr_overdue - prev_overdue):
        changes["overdue_new"].append(overdue_titles.get(tid, tid))
    for tid in sorted(prev_overdue - curr_overdue):
        changes["overdue_cleared"].append(tid)

    prev_approvals = {a.approval_id for a in previous.pending_approvals}
    for a in current.pending_approvals:
        if a.approval_id not in prev_approvals:
            changes["approvals_added"].append(f"{a.summary} [{a.approval_id}]")

    prev_failed = {r.run_id for r in previous.failed_agent_runs}
    for r in current.failed_agent_runs:
        if r.run_id not in prev_failed:
            changes["agent_failures_new"].append(r.agent_id)

    return changes


def describe_changes(changes: dict[str, list[str]]) -> str:
    """Render a diff dict as concise human text; empty string when no change."""
    lines: list[str] = []
    label_map = [
        ("blockers_new", "Newly blocked"),
        ("blockers_resolved", "Blockers resolved"),
        ("overdue_new", "Newly overdue"),
        ("overdue_cleared", "No longer overdue"),
        ("approvals_added", "Approvals now waiting on you"),
        ("agent_failures_new", "Agent failures"),
    ]
    for key, label in label_map:
        items = changes.get(key) or []
        if items:
            lines.append(f"- {label}: " + "; ".join(items))
    return "\n".join(lines)


def get_previous_snapshot() -> CompanySnapshot | None:
    """The superseded snapshot from the last refresh, if any."""
    with _cache_lock:
        return _previous


__all__ = [
    "CompanySnapshot",
    "CompanyStateUnavailable",
    "TaskView",
    "GoalView",
    "ApprovalView",
    "AgentRunView",
    "capture_snapshot",
    "get_snapshot",
    "invalidate_cache",
    "db_path",
    "derived_facts",
    "diff_snapshots",
    "describe_changes",
    "get_previous_snapshot",
]
