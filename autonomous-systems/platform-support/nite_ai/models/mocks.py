"""Deterministic mock providers for routing/fallback tests. No network, no cost."""

from __future__ import annotations

from nite_ai.errors import ErrorCategory
from nite_ai.models.contracts import (
    ModelExecutionMetadata,
    ModelProvider,
    ModelRequest,
    ModelResult,
    ProviderDefinition,
    ProviderStatus,
)


class BaseMockProvider:
    def __init__(self, definition: ProviderDefinition, model_ref: str = "mock-1") -> None:
        self.definition = definition
        self.model_ref = model_ref
        self.calls = 0

    def supports(self, request: ModelRequest) -> bool:
        return self.definition.available

    def health(self) -> ProviderStatus:
        return ProviderStatus(self.definition.provider_id, healthy=self.definition.available)


class EchoProvider(BaseMockProvider):
    """Always succeeds; echoes the last user message."""

    def execute(self, request: ModelRequest) -> ModelResult:
        self.calls += 1
        last = request.messages[-1].get("content", "")
        return ModelResult(
            request_id=request.request_id,
            ok=True,
            content=f"echo:{last}",
            execution=ModelExecutionMetadata(
                provider_id=self.definition.provider_id, model_ref=self.model_ref
            ),
        )


class DeterministicReasoningProvider(BaseMockProvider):
    """Returns fixed structured output for eval-style tests."""

    def __init__(self, definition: ProviderDefinition, payload: dict) -> None:
        super().__init__(definition)
        self._payload = payload

    def execute(self, request: ModelRequest) -> ModelResult:
        self.calls += 1
        return ModelResult(
            request_id=request.request_id,
            ok=True,
            structured=dict(self._payload),
            execution=ModelExecutionMetadata(
                provider_id=self.definition.provider_id, model_ref=self.model_ref
            ),
        )


class FailingProvider(BaseMockProvider):
    """Fails with a configurable category/retryability."""

    def __init__(
        self,
        definition: ProviderDefinition,
        category: ErrorCategory = ErrorCategory.MODEL_FAILURE,
        retryable: bool = True,
        message: str = "mock failure",
    ) -> None:
        super().__init__(definition)
        self.category = category
        self.retryable = retryable
        self.message = message

    def execute(self, request: ModelRequest) -> ModelResult:
        self.calls += 1
        return ModelResult.failure(
            request.request_id,
            self.category,
            self.message,
            retryable=self.retryable,
            provider_id=self.definition.provider_id,
        )


class SlowProvider(BaseMockProvider):
    """Succeeds but records elapsed time; used for timeout-class routing tests."""

    def __init__(self, definition: ProviderDefinition, delay_seconds: float = 0.0) -> None:
        super().__init__(definition)
        self._delay = delay_seconds

    def execute(self, request: ModelRequest) -> ModelResult:
        import time

        time.sleep(self._delay)
        self.calls += 1
        return ModelResult(
            request_id=request.request_id,
            ok=True,
            content="slow-ok",
            execution=ModelExecutionMetadata(
                provider_id=self.definition.provider_id, model_ref=self.model_ref
            ),
        )


class PrivacyRestrictedProvider(EchoProvider):
    """Definition declares a low privacy tier; routing must exclude it for
    sensitive requests even though execute() would succeed."""


__all__ = [
    "BaseMockProvider",
    "DeterministicReasoningProvider",
    "EchoProvider",
    "FailingProvider",
    "PrivacyRestrictedProvider",
    "SlowProvider",
]
