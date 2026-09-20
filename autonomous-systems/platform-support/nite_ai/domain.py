"""Company domain schemas (Phase 4C).

Structured company objects for future Thursday company-state reasoning.
Schema layer only — no persistence here. IDs are stable machine identifiers;
human-readable titles are data fields, never identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nite_ai._serialization import dataclass_to_dict
from nite_ai.errors import ValidationError


class ItemStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class GoalKind(str, Enum):
    COMPANY = "company"
    QUARTERLY = "quarterly"
    MONTHLY = "monthly"
    WEEKLY = "weekly"


def _require_id(value: str, label: str) -> None:
    if not value:
        raise ValidationError(f"{label} must not be empty")


@dataclass(frozen=True)
class Goal:
    goal_id: str
    kind: GoalKind
    title: str
    status: ItemStatus = ItemStatus.DRAFT
    parent_goal_id: str | None = None      # hierarchy: company → quarterly → monthly → weekly
    progress: float = 0.0                  # 0..1
    owner: str = ""
    target_date_epoch: float | None = None
    depends_on: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()       # goal/task ids
    notes: str = ""

    def __post_init__(self) -> None:
        _require_id(self.goal_id, "Goal.goal_id")
        _require_id(self.title, "Goal.title")
        if not 0.0 <= self.progress <= 1.0:
            raise ValidationError("Goal.progress must be within [0, 1]")
        if self.kind is not GoalKind.COMPANY and self.parent_goal_id is None:
            raise ValidationError("non-company goals must declare parent_goal_id")


@dataclass(frozen=True)
class Project:
    project_id: str
    title: str
    goal_id: str
    status: ItemStatus = ItemStatus.DRAFT
    progress: float = 0.0

    def __post_init__(self) -> None:
        _require_id(self.project_id, "Project.project_id")
        _require_id(self.goal_id, "Project.goal_id")


@dataclass(frozen=True)
class Task:
    task_id: str
    title: str
    project_id: str
    status: ItemStatus = ItemStatus.DRAFT
    due_epoch: float | None = None
    priority: int = 0                       # higher = more urgent
    blocked_by: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_id(self.task_id, "Task.task_id")
        _require_id(self.project_id, "Task.project_id")
        if self.status is ItemStatus.BLOCKED and not self.blocked_by:
            raise ValidationError("blocked tasks must reference at least one blocker")


@dataclass(frozen=True)
class AgentStatus:
    agent_id: str
    role: str
    state: str                              # idle / running / failed / ...
    current_task_id: str | None = None
    started_at_epoch: float | None = None
    last_update_epoch: float | None = None
    result_summary: str = ""
    blocker: str = ""
    trace_id: str = ""

    def __post_init__(self) -> None:
        _require_id(self.agent_id, "AgentStatus.agent_id")


@dataclass(frozen=True)
class DailyBriefData:
    """Machine-shaped brief. LLM may phrase it; selection stays deterministic."""

    brief_date: str                         # ISO date
    top_priorities: tuple[str, ...] = ()    # task ids, priority order
    due_today: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    agent_completions: tuple[str, ...] = () # agent ids that completed work
    goals_at_risk: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_id(self.brief_date, "DailyBriefData.brief_date")

    def to_dict(self) -> dict:
        return dataclass_to_dict(self)


@dataclass(frozen=True)
class WeeklyReviewData:
    week_label: str                         # e.g. "2026-W34"
    goals_progress: tuple[tuple[str, float], ...] = ()   # (goal_id, progress)
    completed_task_ids: tuple[str, ...] = ()
    slipped_item_ids: tuple[str, ...] = ()
    decisions_made: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    next_week_priorities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_id(self.week_label, "WeeklyReviewData.week_label")

    def to_dict(self) -> dict:
        d = dataclass_to_dict(self)
        d["goals_progress"] = [[g, p] for g, p in self.goals_progress]
        return d


@dataclass(frozen=True)
class EngineeringStatus:
    """Generic product/engineering snapshot with provenance. Evidence model —
    Git is not the company database; this is a captured, sourced view."""

    product_id: str
    repository: str
    branch: str
    commit_sha: str
    working_tree_state: str            # clean / dirty / unknown
    test_status: str                   # pass / fail / unknown / not_run
    build_status: str = "unknown"
    qualification_status: str = "unknown"
    release_status: str = "unknown"
    blockers: tuple[str, ...] = ()
    source: str = ""                   # e.g. local_git_snapshot, ci_report
    captured_at_epoch: float | None = None

    def __post_init__(self) -> None:
        _require_id(self.product_id, "EngineeringStatus.product_id")
        _require_id(self.repository, "EngineeringStatus.repository")

    def to_dict(self) -> dict:
        return dataclass_to_dict(self)


__all__ = [
    "AgentStatus",
    "DailyBriefData",
    "EngineeringStatus",
    "Goal",
    "GoalKind",
    "ItemStatus",
    "Project",
    "Task",
    "WeeklyReviewData",
]
