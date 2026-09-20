"""Versioned contracts shared across Audio_Too domain boundaries.

These models deliberately use only the Python standard library. They define
wire-safe data, not domain behavior or persistence. Each contract validates on
construction and round-trips through ordinary JSON dictionaries.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar
from uuid import uuid4

CURRENT_SCHEMA_VERSION = 1
MAX_PAYLOAD_BYTES = 256 * 1024
MAX_TEXT_CHARS = 2_048
MAX_ANSWER_CHARS = 64 * 1024
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_HASH_RE = re.compile(r"^sha256:[a-f0-9]{64}$")


class ContractValidationError(ValueError):
    """A boundary-contract validation error with a stable field name."""

    def __init__(self, field_name: str, message: str) -> None:
        super().__init__(f"{field_name}: {message}")
        self.field_name = field_name
        self.message = message


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _identifier(value: object, field_name: str, *, optional: bool = False) -> str:
    text = str(value or "").strip()
    if not text and optional:
        return ""
    if not _ID_RE.fullmatch(text):
        raise ContractValidationError(
            field_name,
            "must be 1-128 characters using letters, numbers, '.', '_', ':', or '-'",
        )
    return text


def _text(
    value: object,
    field_name: str,
    *,
    optional: bool = False,
    limit: int = MAX_TEXT_CHARS,
) -> str:
    text = str(value or "").strip()
    if not text and not optional:
        raise ContractValidationError(field_name, "is required")
    if len(text) > limit:
        raise ContractValidationError(field_name, f"must be {limit:,} characters or fewer")
    return text


def _timestamp(value: object, field_name: str, *, optional: bool = False) -> str:
    text = str(value or "").strip()
    if not text and optional:
        return ""
    if not text:
        raise ContractValidationError(field_name, "is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractValidationError(field_name, "must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ContractValidationError(field_name, "must include a timezone")
    return text


def _json_object(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractValidationError(field_name, "must be a JSON object")
    try:
        encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractValidationError(field_name, "must contain only finite JSON values") from exc
    if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ContractValidationError(
            field_name, f"must be no larger than {MAX_PAYLOAD_BYTES // 1024} KiB"
        )
    return json.loads(encoded)


def _fields(payload: object, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContractValidationError("payload", "must be a JSON object")
    if any(not isinstance(key, str) for key in payload):
        raise ContractValidationError("payload", "field names must be strings")
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ContractValidationError(unknown[0], "is not a supported field")
    return payload


def _version(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractValidationError("schema_version", "must be a positive integer")
    if value < 1:
        raise ContractValidationError("schema_version", "must be a positive integer")
    return value


def _integer(value: object, field_name: str, *, minimum: int, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractValidationError(field_name, "must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        if maximum is None:
            message = f"must be at least {minimum}"
        else:
            message = f"must be from {minimum} to {maximum}"
        raise ContractValidationError(field_name, message)
    return value


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ContractValidationError(field_name, "must be a boolean")
    return value


def _sequence(value: object, field_name: str) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ContractValidationError(field_name, "must be an array")
    return tuple(value)


def _enum(enum_type: type[Enum], value: object, field_name: str) -> Any:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        options = ", ".join(str(item.value) for item in enum_type)
        raise ContractValidationError(field_name, f"must be one of: {options}") from exc


class ResultStatus(str, Enum):
    ACCEPTED = "accepted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PermissionScope(str, Enum):
    READ = "read"
    ANALYZE = "analyze"
    PROPOSE = "propose"
    MUTATE_LOCAL = "mutate_local"
    COMMUNICATE_EXTERNAL = "communicate_external"


class AssistantConfidence(str, Enum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class AssistantResponse:
    """Typed assistant payload embedded inside a ``ResultEnvelope``.

    This is the shared semantic contract for Thursday/KENN responses. Interface-
    specific presentation data belongs in ``metadata``; core routing, grounding,
    sources, and confirmation state remain stable across HTTP, CLI, SSE, and voice.
    """

    answer: str
    session_id: str = ""
    intent: str = ""
    route: str = ""
    service: str = ""
    confidence: AssistantConfidence = AssistantConfidence.UNKNOWN
    grounding: dict[str, Any] = field(default_factory=dict)
    sources: tuple[dict[str, Any], ...] = ()
    requires_confirmation: bool = False
    confirmation_token: str = ""
    suggestions: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = CURRENT_SCHEMA_VERSION

    FIELDS: ClassVar[set[str]] = {
        "schema_version", "answer", "session_id", "intent", "route", "service",
        "confidence", "grounding", "sources", "requires_confirmation",
        "confirmation_token", "suggestions", "metadata",
    }

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _version(self.schema_version))
        object.__setattr__(
            self, "answer", _text(self.answer, "answer", limit=MAX_ANSWER_CHARS)
        )
        for field_name in ("session_id", "intent", "route", "service"):
            object.__setattr__(
                self,
                field_name,
                _identifier(getattr(self, field_name), field_name, optional=True),
            )
        object.__setattr__(
            self,
            "confidence",
            _enum(AssistantConfidence, self.confidence, "confidence"),
        )
        object.__setattr__(self, "grounding", _json_object(self.grounding, "grounding"))
        object.__setattr__(
            self,
            "sources",
            tuple(
                _json_object(item, "sources")
                for item in _sequence(self.sources, "sources")
            ),
        )
        object.__setattr__(
            self,
            "requires_confirmation",
            _boolean(self.requires_confirmation, "requires_confirmation"),
        )
        object.__setattr__(
            self,
            "confirmation_token",
            _identifier(
                self.confirmation_token,
                "confirmation_token",
                optional=True,
            ),
        )
        if self.requires_confirmation and not self.confirmation_token:
            raise ContractValidationError(
                "confirmation_token", "is required when confirmation is required"
            )
        if not self.requires_confirmation and self.confirmation_token:
            raise ContractValidationError(
                "confirmation_token", "is only valid when confirmation is required"
            )
        object.__setattr__(
            self,
            "suggestions",
            tuple(
                _json_object(item, "suggestions")
                for item in _sequence(self.suggestions, "suggestions")
            ),
        )
        object.__setattr__(self, "metadata", _json_object(self.metadata, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "answer": self.answer,
            "session_id": self.session_id,
            "intent": self.intent,
            "route": self.route,
            "service": self.service,
            "confidence": self.confidence.value,
            "grounding": self.grounding,
            "sources": list(self.sources),
            "requires_confirmation": self.requires_confirmation,
            "confirmation_token": self.confirmation_token,
            "suggestions": list(self.suggestions),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: object) -> AssistantResponse:
        data = _fields(payload, cls.FIELDS)
        return cls(
            schema_version=data.get("schema_version", CURRENT_SCHEMA_VERSION),
            answer=data.get("answer", ""),
            session_id=data.get("session_id", ""),
            intent=data.get("intent", ""),
            route=data.get("route", ""),
            service=data.get("service", ""),
            confidence=data.get("confidence", AssistantConfidence.UNKNOWN.value),
            grounding=data.get("grounding", {}),
            sources=_sequence(data.get("sources", ()), "sources"),
            requires_confirmation=_boolean(
                data.get("requires_confirmation", False), "requires_confirmation"
            ),
            confirmation_token=data.get("confirmation_token", ""),
            suggestions=_sequence(data.get("suggestions", ()), "suggestions"),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    kind: str
    media_type: str
    content_hash: str
    uri: str
    producer: str
    producer_version: str
    parent_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    schema_version: int = CURRENT_SCHEMA_VERSION

    FIELDS: ClassVar[set[str]] = {
        "schema_version", "artifact_id", "kind", "media_type", "content_hash", "uri",
        "producer", "producer_version", "parent_ids", "metadata", "created_at",
    }

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _version(self.schema_version))
        object.__setattr__(self, "artifact_id", _identifier(self.artifact_id, "artifact_id"))
        object.__setattr__(self, "kind", _identifier(self.kind, "kind"))
        object.__setattr__(self, "media_type", _text(self.media_type, "media_type", limit=255))
        digest = str(self.content_hash or "").strip().lower()
        if not _HASH_RE.fullmatch(digest):
            raise ContractValidationError("content_hash", "must be 'sha256:' plus 64 hex characters")
        object.__setattr__(self, "content_hash", digest)
        object.__setattr__(self, "uri", _text(self.uri, "uri"))
        object.__setattr__(self, "producer", _identifier(self.producer, "producer"))
        object.__setattr__(
            self, "producer_version", _text(self.producer_version, "producer_version", limit=128)
        )
        object.__setattr__(
            self,
            "parent_ids",
            tuple(_identifier(item, "parent_ids") for item in _sequence(self.parent_ids, "parent_ids")),
        )
        object.__setattr__(self, "metadata", _json_object(self.metadata, "metadata"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "media_type": self.media_type,
            "content_hash": self.content_hash,
            "uri": self.uri,
            "producer": self.producer,
            "producer_version": self.producer_version,
            "parent_ids": list(self.parent_ids),
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: object) -> ArtifactRef:
        data = _fields(payload, cls.FIELDS)
        return cls(
            schema_version=data.get("schema_version", CURRENT_SCHEMA_VERSION),
            artifact_id=data.get("artifact_id", ""),
            kind=data.get("kind", ""),
            media_type=data.get("media_type", ""),
            content_hash=data.get("content_hash", ""),
            uri=data.get("uri", ""),
            producer=data.get("producer", ""),
            producer_version=data.get("producer_version", ""),
            parent_ids=_sequence(data.get("parent_ids", ()), "parent_ids"),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", utc_now()),
        )


@dataclass(frozen=True)
class AudioFeatureSet:
    """An immutable, provenance-bound audio measurement result.

    This is deliberately a data boundary, not a replacement for the richer
    Mix Review report.  Downstream agents can use it to distinguish measured
    facts for one exact source/configuration from suggestions or inferences.
    """

    source_hash: str
    sample_rate: int
    channels: int
    duration_seconds: float
    measurements: dict[str, Any]
    analysis_profile: str
    producer: str
    source_artifact_id: str = ""
    diagnostics: tuple[str, ...] = ()
    measured_at: str = field(default_factory=utc_now)
    schema_version: int = CURRENT_SCHEMA_VERSION

    FIELDS: ClassVar[set[str]] = {
        "schema_version", "source_hash", "source_artifact_id", "sample_rate",
        "channels", "duration_seconds", "measurements", "analysis_profile",
        "producer", "diagnostics", "measured_at",
    }

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _version(self.schema_version))
        digest = str(self.source_hash or "").strip().lower()
        if not _HASH_RE.fullmatch(digest):
            raise ContractValidationError("source_hash", "must be 'sha256:' plus 64 hex characters")
        object.__setattr__(self, "source_hash", digest)
        object.__setattr__(
            self, "source_artifact_id", _identifier(self.source_artifact_id, "source_artifact_id", optional=True)
        )
        object.__setattr__(self, "sample_rate", _integer(self.sample_rate, "sample_rate", minimum=1, maximum=768_000))
        object.__setattr__(self, "channels", _integer(self.channels, "channels", minimum=1, maximum=64))
        duration = self.duration_seconds
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
            raise ContractValidationError("duration_seconds", "must be a finite number greater than or equal to zero")
        object.__setattr__(self, "duration_seconds", float(duration))
        object.__setattr__(self, "measurements", _json_object(self.measurements, "measurements"))
        object.__setattr__(self, "analysis_profile", _identifier(self.analysis_profile, "analysis_profile"))
        object.__setattr__(self, "producer", _identifier(self.producer, "producer"))
        object.__setattr__(
            self, "diagnostics", tuple(_text(item, "diagnostics") for item in _sequence(self.diagnostics, "diagnostics"))
        )
        object.__setattr__(self, "measured_at", _timestamp(self.measured_at, "measured_at"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_hash": self.source_hash,
            "source_artifact_id": self.source_artifact_id,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "duration_seconds": self.duration_seconds,
            "measurements": self.measurements,
            "analysis_profile": self.analysis_profile,
            "producer": self.producer,
            "diagnostics": list(self.diagnostics),
            "measured_at": self.measured_at,
        }

    @classmethod
    def from_dict(cls, payload: object) -> AudioFeatureSet:
        data = _fields(payload, cls.FIELDS)
        return cls(
            schema_version=data.get("schema_version", CURRENT_SCHEMA_VERSION),
            source_hash=data.get("source_hash", ""),
            source_artifact_id=data.get("source_artifact_id", ""),
            sample_rate=data.get("sample_rate", 0),
            channels=data.get("channels", 0),
            duration_seconds=data.get("duration_seconds", -1),
            measurements=data.get("measurements", {}),
            analysis_profile=data.get("analysis_profile", ""),
            producer=data.get("producer", ""),
            diagnostics=_sequence(data.get("diagnostics", ()), "diagnostics"),
            measured_at=data.get("measured_at", utc_now()),
        )


@dataclass(frozen=True)
class CommandEnvelope:
    command_id: str
    capability: str
    actor_id: str
    payload: dict[str, Any]
    correlation_id: str
    project_id: str = ""
    idempotency_key: str = ""
    deadline_at: str = ""
    created_at: str = field(default_factory=utc_now)
    schema_version: int = CURRENT_SCHEMA_VERSION

    FIELDS: ClassVar[set[str]] = {
        "schema_version", "command_id", "capability", "actor_id", "payload",
        "correlation_id", "project_id", "idempotency_key", "deadline_at", "created_at",
    }

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _version(self.schema_version))
        object.__setattr__(self, "command_id", _identifier(self.command_id, "command_id"))
        object.__setattr__(self, "capability", _identifier(self.capability, "capability"))
        object.__setattr__(self, "actor_id", _identifier(self.actor_id, "actor_id"))
        object.__setattr__(self, "payload", _json_object(self.payload, "payload"))
        object.__setattr__(
            self, "correlation_id", _identifier(self.correlation_id, "correlation_id")
        )
        object.__setattr__(
            self, "project_id", _identifier(self.project_id, "project_id", optional=True)
        )
        object.__setattr__(
            self,
            "idempotency_key",
            _identifier(self.idempotency_key, "idempotency_key", optional=True),
        )
        object.__setattr__(
            self, "deadline_at", _timestamp(self.deadline_at, "deadline_at", optional=True)
        )
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))

    @classmethod
    def new(
        cls,
        capability: str,
        actor_id: str,
        payload: dict[str, Any],
        *,
        project_id: str = "",
        idempotency_key: str = "",
        deadline_at: str = "",
        correlation_id: str = "",
    ) -> CommandEnvelope:
        command_id = str(uuid4())
        return cls(
            command_id=command_id,
            capability=capability,
            actor_id=actor_id,
            payload=payload,
            correlation_id=correlation_id or command_id,
            project_id=project_id,
            idempotency_key=idempotency_key,
            deadline_at=deadline_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "command_id": self.command_id,
            "capability": self.capability,
            "actor_id": self.actor_id,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "project_id": self.project_id,
            "idempotency_key": self.idempotency_key,
            "deadline_at": self.deadline_at,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: object) -> CommandEnvelope:
        data = _fields(payload, cls.FIELDS)
        return cls(
            schema_version=data.get("schema_version", CURRENT_SCHEMA_VERSION),
            command_id=data.get("command_id", ""),
            capability=data.get("capability", ""),
            actor_id=data.get("actor_id", ""),
            payload=data.get("payload", {}),
            correlation_id=data.get("correlation_id", ""),
            project_id=data.get("project_id", ""),
            idempotency_key=data.get("idempotency_key", ""),
            deadline_at=data.get("deadline_at", ""),
            created_at=data.get("created_at", utc_now()),
        )


@dataclass(frozen=True)
class ContractError:
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _identifier(self.code, "error.code"))
        object.__setattr__(self, "message", _text(self.message, "error.message"))
        object.__setattr__(self, "retryable", _boolean(self.retryable, "error.retryable"))
        object.__setattr__(self, "details", _json_object(self.details, "error.details"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": bool(self.retryable),
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, payload: object) -> ContractError:
        data = _fields(payload, {"code", "message", "retryable", "details"})
        return cls(
            code=data.get("code", ""),
            message=data.get("message", ""),
            retryable=_boolean(data.get("retryable", False), "error.retryable"),
            details=data.get("details", {}),
        )


@dataclass(frozen=True)
class ResultEnvelope:
    command_id: str
    status: ResultStatus
    result: dict[str, Any]
    correlation_id: str
    artifacts: tuple[ArtifactRef, ...] = ()
    warnings: tuple[str, ...] = ()
    error: ContractError | None = None
    completed_at: str = field(default_factory=utc_now)
    schema_version: int = CURRENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _version(self.schema_version))
        object.__setattr__(self, "command_id", _identifier(self.command_id, "command_id"))
        object.__setattr__(self, "status", _enum(ResultStatus, self.status, "status"))
        object.__setattr__(self, "result", _json_object(self.result, "result"))
        object.__setattr__(
            self, "correlation_id", _identifier(self.correlation_id, "correlation_id")
        )
        artifacts = _sequence(self.artifacts, "artifacts")
        if any(not isinstance(item, ArtifactRef) for item in artifacts):
            raise ContractValidationError("artifacts", "must contain ArtifactRef values")
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(
            self,
            "warnings",
            tuple(_text(item, "warnings") for item in _sequence(self.warnings, "warnings")),
        )
        object.__setattr__(self, "completed_at", _timestamp(self.completed_at, "completed_at"))
        if self.status == ResultStatus.FAILED and self.error is None:
            raise ContractValidationError("error", "is required when status is failed")
        if self.status != ResultStatus.FAILED and self.error is not None:
            raise ContractValidationError("error", "is only valid when status is failed")
        if self.error is not None and not isinstance(self.error, ContractError):
            raise ContractValidationError("error", "must be a ContractError")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "command_id": self.command_id,
            "status": self.status.value,
            "result": self.result,
            "correlation_id": self.correlation_id,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "warnings": list(self.warnings),
            "error": self.error.to_dict() if self.error else None,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, payload: object) -> ResultEnvelope:
        allowed = {
            "schema_version", "command_id", "status", "result", "correlation_id",
            "artifacts", "warnings", "error", "completed_at",
        }
        data = _fields(payload, allowed)
        raw_error = data.get("error")
        return cls(
            schema_version=data.get("schema_version", CURRENT_SCHEMA_VERSION),
            command_id=data.get("command_id", ""),
            status=data.get("status", ""),
            result=data.get("result", {}),
            correlation_id=data.get("correlation_id", ""),
            artifacts=tuple(
                ArtifactRef.from_dict(item)
                for item in _sequence(data.get("artifacts", ()), "artifacts")
            ),
            warnings=_sequence(data.get("warnings", ()), "warnings"),
            error=ContractError.from_dict(raw_error) if raw_error is not None else None,
            completed_at=data.get("completed_at", utc_now()),
        )


@dataclass(frozen=True)
class JobSnapshot:
    job_id: str
    capability: str
    status: JobStatus
    stage: str
    progress: int = 0
    command_id: str = ""
    correlation_id: str = ""
    project_id: str = ""
    attempt: int = 0
    max_attempts: int = 3
    worker_id: str = ""
    result_artifact_ids: tuple[str, ...] = ()
    error: ContractError | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    lease_expires_at: str = ""
    schema_version: int = CURRENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _version(self.schema_version))
        object.__setattr__(self, "job_id", _identifier(self.job_id, "job_id"))
        object.__setattr__(self, "capability", _identifier(self.capability, "capability"))
        object.__setattr__(self, "status", _enum(JobStatus, self.status, "status"))
        object.__setattr__(self, "stage", _identifier(self.stage, "stage"))
        object.__setattr__(
            self, "progress", _integer(self.progress, "progress", minimum=0, maximum=100)
        )
        for field_name in ("command_id", "correlation_id", "project_id", "worker_id"):
            object.__setattr__(
                self,
                field_name,
                _identifier(getattr(self, field_name), field_name, optional=True),
            )
        object.__setattr__(self, "attempt", _integer(self.attempt, "attempt", minimum=0))
        object.__setattr__(
            self, "max_attempts", _integer(self.max_attempts, "max_attempts", minimum=1)
        )
        object.__setattr__(
            self,
            "result_artifact_ids",
            tuple(
                _identifier(item, "result_artifact_ids")
                for item in _sequence(self.result_artifact_ids, "result_artifact_ids")
            ),
        )
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _timestamp(self.updated_at, "updated_at"))
        object.__setattr__(
            self,
            "lease_expires_at",
            _timestamp(self.lease_expires_at, "lease_expires_at", optional=True),
        )
        if self.status == JobStatus.FAILED and self.error is None:
            raise ContractValidationError("error", "is required when a job has failed")
        if self.status != JobStatus.FAILED and self.error is not None:
            raise ContractValidationError("error", "is only valid when a job has failed")
        if self.error is not None and not isinstance(self.error, ContractError):
            raise ContractValidationError("error", "must be a ContractError")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "capability": self.capability,
            "status": self.status.value,
            "stage": self.stage,
            "progress": self.progress,
            "command_id": self.command_id,
            "correlation_id": self.correlation_id,
            "project_id": self.project_id,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "worker_id": self.worker_id,
            "result_artifact_ids": list(self.result_artifact_ids),
            "error": self.error.to_dict() if self.error else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "lease_expires_at": self.lease_expires_at,
        }

    @classmethod
    def from_dict(cls, payload: object) -> JobSnapshot:
        data = _fields(payload, set(cls.__dataclass_fields__) - {"FIELDS"})
        raw_error = data.get("error")
        return cls(
            schema_version=data.get("schema_version", CURRENT_SCHEMA_VERSION),
            job_id=data.get("job_id", ""),
            capability=data.get("capability", ""),
            status=data.get("status", ""),
            stage=data.get("stage", ""),
            progress=data.get("progress", 0),
            command_id=data.get("command_id", ""),
            correlation_id=data.get("correlation_id", ""),
            project_id=data.get("project_id", ""),
            attempt=data.get("attempt", 0),
            max_attempts=data.get("max_attempts", 3),
            worker_id=data.get("worker_id", ""),
            result_artifact_ids=_sequence(
                data.get("result_artifact_ids", ()), "result_artifact_ids"
            ),
            error=ContractError.from_dict(raw_error) if raw_error is not None else None,
            created_at=data.get("created_at", utc_now()),
            updated_at=data.get("updated_at", utc_now()),
            lease_expires_at=data.get("lease_expires_at", ""),
        )


@dataclass(frozen=True)
class DomainEvent:
    event_id: str
    event_type: str
    aggregate_id: str
    correlation_id: str
    actor_id: str
    payload: dict[str, Any]
    occurred_at: str = field(default_factory=utc_now)
    schema_version: int = CURRENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _version(self.schema_version))
        for field_name in ("event_id", "event_type", "aggregate_id", "correlation_id", "actor_id"):
            object.__setattr__(self, field_name, _identifier(getattr(self, field_name), field_name))
        object.__setattr__(self, "payload", _json_object(self.payload, "payload"))
        object.__setattr__(self, "occurred_at", _timestamp(self.occurred_at, "occurred_at"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_id": self.aggregate_id,
            "correlation_id": self.correlation_id,
            "actor_id": self.actor_id,
            "payload": self.payload,
            "occurred_at": self.occurred_at,
        }

    @classmethod
    def from_dict(cls, payload: object) -> DomainEvent:
        data = _fields(payload, set(cls.__dataclass_fields__) - {"FIELDS"})
        return cls(
            schema_version=data.get("schema_version", CURRENT_SCHEMA_VERSION),
            event_id=data.get("event_id", ""),
            event_type=data.get("event_type", ""),
            aggregate_id=data.get("aggregate_id", ""),
            correlation_id=data.get("correlation_id", ""),
            actor_id=data.get("actor_id", ""),
            payload=data.get("payload", {}),
            occurred_at=data.get("occurred_at", utc_now()),
        )


@dataclass(frozen=True)
class Capability:
    name: str
    version: str
    description: str
    permissions: tuple[PermissionScope, ...]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    resource_needs: dict[str, Any] = field(default_factory=dict)
    schema_version: int = CURRENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _version(self.schema_version))
        object.__setattr__(self, "name", _identifier(self.name, "name"))
        object.__setattr__(self, "version", _text(self.version, "version", limit=128))
        object.__setattr__(self, "description", _text(self.description, "description"))
        object.__setattr__(
            self,
            "permissions",
            tuple(
                _enum(PermissionScope, item, "permissions")
                for item in _sequence(self.permissions, "permissions")
            ),
        )
        if len(set(self.permissions)) != len(self.permissions):
            raise ContractValidationError("permissions", "must not contain duplicates")
        object.__setattr__(self, "input_schema", _json_object(self.input_schema, "input_schema"))
        object.__setattr__(self, "output_schema", _json_object(self.output_schema, "output_schema"))
        object.__setattr__(
            self, "resource_needs", _json_object(self.resource_needs, "resource_needs")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "permissions": [item.value for item in self.permissions],
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "resource_needs": self.resource_needs,
        }

    @classmethod
    def from_dict(cls, payload: object) -> Capability:
        data = _fields(payload, set(cls.__dataclass_fields__) - {"FIELDS"})
        return cls(
            schema_version=data.get("schema_version", CURRENT_SCHEMA_VERSION),
            name=data.get("name", ""),
            version=data.get("version", ""),
            description=data.get("description", ""),
            permissions=_sequence(data.get("permissions", ()), "permissions"),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            resource_needs=data.get("resource_needs", {}),
        )


@dataclass(frozen=True)
class ProjectContext:
    project_id: str
    intent: str
    reference_artifact_ids: tuple[str, ...] = ()
    preferences: dict[str, Any] = field(default_factory=dict)
    decisions: tuple[dict[str, Any], ...] = ()
    updated_at: str = field(default_factory=utc_now)
    schema_version: int = CURRENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _version(self.schema_version))
        object.__setattr__(self, "project_id", _identifier(self.project_id, "project_id"))
        object.__setattr__(self, "intent", _text(self.intent, "intent", optional=True))
        object.__setattr__(
            self,
            "reference_artifact_ids",
            tuple(
                _identifier(item, "reference_artifact_ids")
                for item in _sequence(self.reference_artifact_ids, "reference_artifact_ids")
            ),
        )
        object.__setattr__(self, "preferences", _json_object(self.preferences, "preferences"))
        object.__setattr__(
            self,
            "decisions",
            tuple(
                _json_object(item, "decisions")
                for item in _sequence(self.decisions, "decisions")
            ),
        )
        object.__setattr__(self, "updated_at", _timestamp(self.updated_at, "updated_at"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "intent": self.intent,
            "reference_artifact_ids": list(self.reference_artifact_ids),
            "preferences": self.preferences,
            "decisions": list(self.decisions),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: object) -> ProjectContext:
        data = _fields(payload, set(cls.__dataclass_fields__) - {"FIELDS"})
        return cls(
            schema_version=data.get("schema_version", CURRENT_SCHEMA_VERSION),
            project_id=data.get("project_id", ""),
            intent=data.get("intent", ""),
            reference_artifact_ids=_sequence(
                data.get("reference_artifact_ids", ()), "reference_artifact_ids"
            ),
            preferences=data.get("preferences", {}),
            decisions=_sequence(data.get("decisions", ()), "decisions"),
            updated_at=data.get("updated_at", utc_now()),
        )
