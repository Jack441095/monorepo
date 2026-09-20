"""Working-memory and task-lifecycle contracts (Phase 4B/4D).

Execution-scoped only — no durable store. A TaskState machine with the states
the Phase-1 architecture actually requires, plus scratch values and decision
records for traceable execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nite_ai._serialization import dataclass_to_dict
from nite_ai.errors import ValidationError


class TaskStatus(str, Enum):
    RECEIVED = "received"
    PLANNED = "planned"
    RUNNING = "running"
    WAITING_TOOL = "waiting_tool"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[str]] = {
    TaskStatus.RECEIVED: frozenset({"planned", "running", "cancelled", "failed"}),
    TaskStatus.PLANNED: frozenset({"running", "cancelled", "failed"}),
    TaskStatus.RUNNING: frozenset(
        {"waiting_tool", "waiting_approval", "completed", "failed", "cancelled"}
    ),
    TaskStatus.WAITING_TOOL: frozenset({"running", "failed", "cancelled"}),
    TaskStatus.WAITING_APPROVAL: frozenset({"running", "cancelled"}),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


def can_transition(current: TaskStatus, nxt: TaskStatus) -> bool:
    return nxt.value in _ALLOWED_TRANSITIONS[current]


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    description: str          # what was decided (machine text, not UI prose)
    basis_refs: tuple[str, ...] = ()   # evidence/context ref ids supporting it
    made_at_epoch: float | None = None

    def __post_init__(self) -> None:
        if not self.decision_id or not self.description:
            raise ValidationError("DecisionRecord requires id and description")


@dataclass(frozen=True)
class WorkingMemory:
    """Execution-scoped memory: task state, scratch values, notes, decisions."""

    task_id: str
    status: TaskStatus = TaskStatus.RECEIVED
    attempt: int = 1
    scratch: dict[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    decisions: tuple[DecisionRecord, ...] = ()

    def __post_init__(self) -> None:
        if not self.task_id:
            raise ValidationError("WorkingMemory.task_id must not be empty")
        if self.attempt < 1:
            raise ValidationError("WorkingMemory.attempt must be >= 1")

    def transition(self, nxt: TaskStatus) -> "WorkingMemory":
        if not can_transition(self.status, nxt):
            raise ValidationError(f"illegal task transition {self.status.value} -> {nxt.value}")
        from dataclasses import replace

        return replace(self, status=nxt)

    def to_dict(self) -> dict:
        return dataclass_to_dict(self)


__all__ = ["DecisionRecord", "TaskStatus", "WorkingMemory", "can_transition"]
