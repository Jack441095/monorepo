"""Telemetry contracts and lightweight trace context.

Contracts only — no backend. Events are metadata-only by design: there is no
field that could carry private user or audio content.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from enum import Enum

from nite_ai._serialization import dataclass_to_dict
from nite_ai.errors import ValidationError


def new_trace_id() -> str:
    return uuid.uuid4().hex


def new_span_id() -> str:
    return uuid.uuid4().hex[:16]


@dataclass(frozen=True)
class TraceContext:
    """Lightweight W3C-style trace identity for execution chains."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    task_id: str | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        hex_re = re.compile(r"^[0-9a-f]{8,32}$")
        for label in ("trace_id", "span_id"):
            value = getattr(self, label)
            if not hex_re.match(value):
                raise ValidationError(
                    f"TraceContext.{label} must be 8-32 lowercase hex chars, got {value!r}"
                )
        if self.parent_span_id is not None and not hex_re.match(self.parent_span_id):
            raise ValidationError("TraceContext.parent_span_id must be hex or None")

    def child(self, task_id: str | None = None, request_id: str | None = None) -> "TraceContext":
        return TraceContext(
            trace_id=self.trace_id,
            span_id=new_span_id(),
            parent_span_id=self.span_id,
            task_id=task_id or self.task_id,
            request_id=request_id or self.request_id,
        )


class TaskEventKind(str, Enum):
    TASK_RECEIVED = "task_received"
    TASK_ROUTED = "task_routed"
    CAPABILITY_CALLED = "capability_called"
    TOOL_CALLED = "tool_called"
    RETRYING = "retrying"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"


@dataclass(frozen=True)
class TaskEvent:
    """One observable step of an execution. Metadata only — never content."""

    event: TaskEventKind
    trace_id: str
    timestamp_epoch: float
    agent_id: str = ""
    capability_id: str = ""
    tool_id: str = ""
    model_ref: str = ""
    duration_ms: float | None = None
    status: str = ""
    retry_count: int = 0
    tokens_in: int | None = None
    tokens_out: int | None = None
    cache_hit: bool | None = None
    error_code: str = ""

    def __post_init__(self) -> None:
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValidationError("TaskEvent.duration_ms must be non-negative")
        if self.retry_count < 0:
            raise ValidationError("TaskEvent.retry_count must be non-negative")
        if self.tokens_in is not None and self.tokens_in < 0:
            raise ValidationError("TaskEvent.tokens_in must be non-negative")

    def to_dict(self) -> dict:
        return dataclass_to_dict(self)


__all__ = ["TaskEvent", "TaskEventKind", "TraceContext", "new_span_id", "new_trace_id"]
