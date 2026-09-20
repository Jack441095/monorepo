"""Tool contracts — generic definitions and results, no product logic."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nite_ai._serialization import dataclass_to_dict, json_schema_for
from nite_ai.contracts.agent import ResultStatus, validate_capability_id
from nite_ai.contracts.artifact import ArtifactRef
from nite_ai.errors import AgentError, RetryPolicy, ValidationError
from nite_ai.permissions import ActionRisk, Permission

_TOOL_ID_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")


def validate_tool_id(tool_id: str) -> None:
    if not _TOOL_ID_RE.match(tool_id):
        raise ValidationError(f"tool id must be dotted lowercase segments, got {tool_id!r}")


class LatencyClass(str, Enum):
    REALTIME = "realtime"          # <20 ms budget
    INTERACTIVE = "interactive"    # <500 ms
    FAST_ANALYSIS = "fast_analysis"  # <5 s
    DEEP_ANALYSIS = "deep_analysis"  # <60 s
    BACKGROUND = "background"      # bounded but long


@dataclass(frozen=True)
class ToolDefinition:
    """Declarative tool description. The platform never implements product tools."""

    tool_id: str
    version: str
    description: str
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    permissions: tuple[Permission, ...] = (Permission.READ,)
    risk: ActionRisk = ActionRisk.LOW
    latency_class: LatencyClass = LatencyClass.INTERACTIVE
    timeout_seconds: float = 30.0
    retry_policy: RetryPolicy = RetryPolicy()
    deterministic: bool = True
    available: bool = True
    provider_id: str | None = None   # IoC: registered by products; never imported here

    def __post_init__(self) -> None:
        validate_tool_id(self.tool_id)
        if not self.version:
            raise ValidationError("ToolDefinition.version must not be empty")
        if self.timeout_seconds <= 0:
            raise ValidationError("ToolDefinition.timeout_seconds must be > 0")
        if self.risk.requires_elevated_permissions and len(self.permissions) == 0:
            raise ValidationError("elevated-risk tools must declare permissions")

    def to_dict(self) -> dict:
        return dataclass_to_dict(self)


@dataclass(frozen=True)
class ToolRequest:
    tool_id: str
    request_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None
    granted_permissions: tuple[Permission, ...] = ()
    deadline_epoch: float | None = None

    def __post_init__(self) -> None:
        validate_tool_id(self.tool_id)
        if not self.request_id:
            raise ValidationError("ToolRequest.request_id must not be empty")


@dataclass(frozen=True)
class ToolResult:
    """Terminal outcome of a tool call. Structured — never raw terminal text."""

    request_id: str
    status: ResultStatus
    payload: dict[str, Any] | None = None
    artifacts: tuple[ArtifactRef, ...] = ()
    warnings: tuple[str, ...] = ()
    error: AgentError | None = None
    metrics: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValidationError("ToolResult.request_id must not be empty")
        if self.status is ResultStatus.SUCCESS and self.payload is None and not self.artifacts:
            raise ValidationError("SUCCESS ToolResult requires payload or artifacts")
        if (
            self.status in {ResultStatus.FAILED, ResultStatus.CANCELLED, ResultStatus.TIMEOUT}
            and self.error is None
        ):
            raise ValidationError(f"{self.status.value} ToolResult requires a structured error")

    @property
    def ok(self) -> bool:
        return self.status in {ResultStatus.SUCCESS, ResultStatus.PARTIAL}

    def to_dict(self) -> dict:
        return dataclass_to_dict(self)


def tool_definition_json_schema() -> dict:
    return json_schema_for(ToolDefinition)


__all__ = [
    "LatencyClass",
    "ToolDefinition",
    "ToolRequest",
    "ToolResult",
    "tool_definition_json_schema",
]
