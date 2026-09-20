"""Provider-neutral model contracts (Phase 2).

Small orthogonal schemas derived from the Phase-2A audit of
`audio_too.model_runtime`. No provider SDKs, no network on import,
deterministic serialization. Sync-first: the existing product runtimes are
synchronous; streaming is declared, implemented only when a consumer exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from nite_ai._serialization import dataclass_to_dict
from nite_ai.contracts.tool import LatencyClass
from nite_ai.errors import AgentError, ErrorCategory, ValidationError
from nite_ai.permissions import PrivacyClass


class ModelCapability(str, Enum):
    TEXT_REASONING = "text_reasoning"
    STRUCTURED_OUTPUT = "structured_output"
    EMBEDDING = "embedding"
    AUDIO_CLASSIFICATION = "audio_classification"
    AUDIO_EMBEDDING = "audio_embedding"


class CostClass(str, Enum):
    FREE_LOCAL = "free_local"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class StructuredOutputSpec:
    """Request machine-checkable structured output (OpenAI-style json_schema)."""

    name: str
    schema: dict

    def __post_init__(self) -> None:
        if not self.name or not self.schema:
            raise ValidationError("StructuredOutputSpec requires name and schema")


@dataclass(frozen=True)
class ModelConstraints:
    """Hard constraints for a model call. Routing must never violate these."""

    allowed_privacy_classes: frozenset[PrivacyClass] = frozenset(
        {PrivacyClass.PUBLIC, PrivacyClass.USER_TEXT}
    )
    local_only: bool = False
    remote_allowed: bool = True
    latency_class: LatencyClass = LatencyClass.INTERACTIVE
    max_cost_class: CostClass = CostClass.MEDIUM
    require_structured_output: bool = False
    require_streaming: bool = False

    def __post_init__(self) -> None:
        if self.local_only and self.remote_allowed:
            # local_only is the stronger statement; normalise remote off.
            object.__setattr__(self, "remote_allowed", False)

    def permits(self, privacy: PrivacyClass) -> bool:
        return privacy in self.allowed_privacy_classes


_COST_ORDER = {
    CostClass.FREE_LOCAL: 0,
    CostClass.LOW: 1,
    CostClass.MEDIUM: 2,
    CostClass.HIGH: 3,
}


@dataclass(frozen=True)
class ProviderDefinition:
    """Declarative description of a model provider. IoC: registered, never imported."""

    provider_id: str                       # e.g. "ollama.local", "openai.remote"
    version: str
    capabilities: tuple[ModelCapability, ...]
    local: bool
    max_privacy_class: PrivacyClass        # highest data sensitivity it may touch
    cost_class: CostClass = CostClass.FREE_LOCAL
    latency_class: LatencyClass = LatencyClass.INTERACTIVE
    supports_structured_output: bool = True
    supports_streaming: bool = False
    available: bool = True                 # dynamic state lives in ProviderStatus
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider_id:
            raise ValidationError("ProviderDefinition.provider_id must not be empty")
        if not self.capabilities:
            raise ValidationError("ProviderDefinition must declare at least one capability")
        if len(self.metadata) > 32:
            raise ValidationError("ProviderDefinition.metadata limited to 32 keys")

    def can_handle_privacy(self, privacy: PrivacyClass) -> bool:
        order = list(PrivacyClass)
        return order.index(privacy) <= order.index(self.max_privacy_class)


@dataclass(frozen=True)
class ProviderStatus:
    """Dynamic availability state — separate from the static definition."""

    provider_id: str
    healthy: bool = True
    detail: str = ""
    consecutive_failures: int = 0


@dataclass(frozen=True)
class ModelRequest:
    request_id: str
    trace_id: str
    messages: tuple[dict[str, str], ...]
    constraints: ModelConstraints = ModelConstraints()
    structured_output: StructuredOutputSpec | None = None
    stream: bool = False
    timeout_seconds: float = 30.0
    preferred_provider_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id or not self.trace_id:
            raise ValidationError("ModelRequest requires request_id and trace_id")
        if not self.messages:
            raise ValidationError("ModelRequest requires at least one message")
        if self.timeout_seconds <= 0:
            raise ValidationError("ModelRequest.timeout_seconds must be > 0")

    def to_dict(self) -> dict:
        return dataclass_to_dict(self)


@dataclass(frozen=True)
class StreamChunk:
    sequence: int
    text_delta: str
    final: bool = False

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValidationError("StreamChunk.sequence must be non-negative")


@dataclass(frozen=True)
class ModelExecutionMetadata:
    provider_id: str
    model_ref: str
    duration_ms: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    attempt: int = 1
    fallback_from_provider_id: str | None = None
    fallback_reason: str = ""


@dataclass(frozen=True)
class ModelResult:
    """Terminal outcome of one model execution."""

    request_id: str
    ok: bool
    content: str = ""
    structured: dict[str, Any] | None = None
    error: AgentError | None = None
    chunks: tuple[StreamChunk, ...] = ()
    execution: ModelExecutionMetadata | None = None

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValidationError("ModelResult.request_id must not be empty")
        if self.ok and not self.content and self.chunks == () and self.structured is None:
            raise ValidationError(
                "successful ModelResult requires content, structured output, or chunks"
            )
        if not self.ok and self.error is None:
            raise ValidationError("failed ModelResult requires a structured error")

    @classmethod
    def failure(
        cls, request_id: str, category: ErrorCategory, message: str, *,
        retryable: bool | None = None, provider_id: str = "",
    ) -> "ModelResult":
        return cls(
            request_id=request_id,
            ok=False,
            error=AgentError(category=category, message=message, retryable=retryable),
            execution=(
                ModelExecutionMetadata(provider_id=provider_id, model_ref="")
                if provider_id else None
            ),
        )

    def to_dict(self) -> dict:
        return dataclass_to_dict(self)


class ModelProvider(Protocol):
    """Executor interface. The platform depends on this protocol, not SDKs.

    Mirrors audio_too's sync `generate` shape (see
    docs/PHASE2_MODEL_RUNTIME_AUDIT.md); `supports()` lets routing pre-filter
    without calling.
    """

    definition: ProviderDefinition

    def supports(self, request: ModelRequest) -> bool: ...

    def execute(self, request: ModelRequest) -> ModelResult: ...

    def health(self) -> ProviderStatus: ...


__all__ = [
    "CostClass",
    "ModelCapability",
    "ModelConstraints",
    "ModelExecutionMetadata",
    "ModelProvider",
    "ModelRequest",
    "ModelResult",
    "ProviderDefinition",
    "ProviderStatus",
    "StreamChunk",
    "StructuredOutputSpec",
]
