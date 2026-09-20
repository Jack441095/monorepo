"""Agent request/result contracts.

Reconciles Thursday's ServiceDef/Capability flow with KENN's
AgentRequest/AgentResult: a stable, language-neutral machine envelope in which
success/failure is explicit — consumers never parse prose to learn the outcome.
Presentation text is NOT part of these contracts (localisation boundary).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nite_ai._serialization import dataclass_to_dict, json_schema_for
from nite_ai.contracts.artifact import ArtifactRef
from nite_ai.contracts.evidence import EvidencePacket
from nite_ai.errors import AgentError, ValidationError
from nite_ai.permissions import ActionRisk, Permission, PrivacyClass

_CAP_ID_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
_LOC_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")


def validate_capability_id(capability_id: str) -> None:
    if not _CAP_ID_RE.match(capability_id):
        raise ValidationError(
            f"capability id must be dotted lowercase segments "
            f"(e.g. 'audio.mix.analyze'), got {capability_id!r}"
        )


class RequestPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class ResultStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class AgentRequest:
    """Stable machine envelope for work entering an agent/capability."""

    request_id: str
    trace_id: str
    capability_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    context_ref: str | None = None          # reference into context store, never inline history
    locale: str = "en"                       # BCP-47-ish tag; presentation concern only
    priority: RequestPriority = RequestPriority.NORMAL
    granted_permissions: tuple[Permission, ...] = ()
    privacy_class: PrivacyClass = PrivacyClass.USER_TEXT
    metadata: dict[str, str] = field(default_factory=dict)
    created_at_epoch: float | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("request_id", self.request_id),
            ("trace_id", self.trace_id),
        ):
            if not value or not isinstance(value, str):
                raise ValidationError(f"AgentRequest.{label} must be a non-empty string")
        validate_capability_id(self.capability_id)
        if not _LOC_RE.match(self.locale):
            raise ValidationError(f"AgentRequest.locale must be a BCP-47-style tag, got {self.locale!r}")
        if self.privacy_class is PrivacyClass.SECRET:
            raise ValidationError(
                "SECRET data may not travel inside an AgentRequest payload"
            )

    def to_dict(self) -> dict:
        return dataclass_to_dict(self)


@dataclass(frozen=True)
class ExecutionMetadata:
    started_at_epoch: float | None = None
    finished_at_epoch: float | None = None
    duration_ms: float | None = None
    attempt: int = 1
    executor_id: str = ""
    model_ref: str | None = None

    def __post_init__(self) -> None:
        if self.attempt < 1:
            raise ValidationError("ExecutionMetadata.attempt must be >= 1")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValidationError("ExecutionMetadata.duration_ms must be non-negative")


@dataclass(frozen=True)
class AgentResult:
    """Terminal outcome of one agent/capability execution."""

    request_id: str
    status: ResultStatus
    result: dict[str, Any] | None = None     # structured machine result
    evidence: EvidencePacket | None = None
    artifacts: tuple[ArtifactRef, ...] = ()
    warnings: tuple[str, ...] = ()
    error: AgentError | None = None
    execution: ExecutionMetadata | None = None

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValidationError("AgentResult.request_id must not be empty")
        terminal_ok = {ResultStatus.SUCCESS, ResultStatus.PARTIAL}
        if self.status in terminal_ok and self.result is None and not self.artifacts:
            raise ValidationError(f"{self.status.value} result requires a result payload or artifacts")
        if self.status in {ResultStatus.FAILED, ResultStatus.CANCELLED, ResultStatus.TIMEOUT}:
            if self.error is None:
                raise ValidationError(f"{self.status.value} result requires a structured error")
        if self.error is not None and self.status in terminal_ok and self.status is ResultStatus.SUCCESS:
            raise ValidationError("SUCCESS result must not carry an error")
        if self.warnings and not all(isinstance(w, str) for w in self.warnings):
            raise ValidationError("AgentResult.warnings must be strings")

    @property
    def ok(self) -> bool:
        return self.status in {ResultStatus.SUCCESS, ResultStatus.PARTIAL}

    def to_dict(self) -> dict:
        return dataclass_to_dict(self)


def agent_request_json_schema() -> dict:
    return json_schema_for(AgentRequest)


def agent_result_json_schema() -> dict:
    return json_schema_for(AgentResult)


# ActionRisk/Permission re-exported here so consumers have one contracts surface.
__all__ = [
    "ActionRisk",
    "AgentRequest",
    "AgentResult",
    "ExecutionMetadata",
    "Permission",
    "RequestPriority",
    "ResultStatus",
    "agent_request_json_schema",
    "agent_result_json_schema",
]
