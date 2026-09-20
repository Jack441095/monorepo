"""Minimal typed message envelope for inter-agent task results.

This exists only as an adapter at orchestration boundaries — the DAG
executor in `thursday.taskgraph` — converting the already-typed
`SubagentResult`/`StepResult`, or a plain-string service handler output,
into one common shape. It does not replace those types and it is never
required inside `registry/handlers.py`'s ~50 handler functions, which keep
returning raw strings as they always have.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from thursday.orchestrator import StepResult
    from thursday.subagent_runtime import SubagentResult


class MessageType(Enum):
    ARTIFACT = "artifact"
    ERROR = "error"
    STATUS = "status"


@dataclass(frozen=True)
class TaskMessage:
    """A typed envelope for one task node's output, produced at DAG-executor
    boundaries only."""

    task_id: str
    sender: str
    payload: str
    message_type: MessageType
    recipient: str | None = None
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.message_type != MessageType.ERROR


def from_subagent_result(
    task_id: str, result: "SubagentResult", *, recipient: str | None = None,
) -> TaskMessage:
    """Adapt a `SubagentRuntime` dispatch result into a `TaskMessage`."""
    return TaskMessage(
        task_id=task_id,
        sender=result.agent,
        recipient=recipient,
        payload=result.output if result.ok else result.error,
        message_type=MessageType.ARTIFACT if result.ok else MessageType.ERROR,
        metadata=dict(result.metadata),
    )


def from_step_result(
    task_id: str, step_result: "StepResult", *, recipient: str | None = None,
) -> TaskMessage:
    """Adapt a brain-plan `StepResult` into a `TaskMessage`."""
    return TaskMessage(
        task_id=task_id,
        sender=step_result.service_id,
        recipient=recipient,
        payload=step_result.output,
        message_type=MessageType.ARTIFACT if step_result.ok else MessageType.ERROR,
    )


def from_raw(
    task_id: str, service_id: str, output: str, *, recipient: str | None = None,
) -> TaskMessage:
    """Wrap a plain-string service handler output — the shape returned by
    every `ServiceDef.action` today — into a `TaskMessage`."""
    return TaskMessage(
        task_id=task_id,
        sender=service_id,
        recipient=recipient,
        payload=output,
        message_type=MessageType.ARTIFACT,
    )
