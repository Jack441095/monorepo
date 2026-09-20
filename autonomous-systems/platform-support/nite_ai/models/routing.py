"""Deterministic model routing with bounded fallback (Phases 2D/2E).

Routing rules:
- constraints are HARD: privacy tier, local-only, cost ceiling, structured
  output, streaming, availability. A non-compliant provider is never selected
  and never receives fallback traffic.
- preferred provider is tried first when compliant; otherwise deterministic
  order: local before remote, cheaper before expensive, then provider_id.
- fallback is bounded by `max_attempts`, never crosses a disallowed privacy
  tier (local-only never reaches remote), and every fallback is reported with
  a reason in the execution metadata.
- no compliant provider at all -> structured failure, never a silent downgrade.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from nite_ai.errors import ErrorCategory
from nite_ai.models.contracts import (
    _COST_ORDER,
    ModelProvider,
    ModelRequest,
    ModelResult,
)
from nite_ai.models.registry import ProviderRegistry
from nite_ai.permissions import PrivacyClass

_MAX_ROUTE_ATTEMPTS = 4


@dataclass(frozen=True)
class RoutingDecision:
    """Deterministic explanation of the chosen candidate order."""

    candidate_order: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]   # (provider_id, reason)
    pinned_unavailable: bool = False


def _strictest_privacy(request: ModelRequest) -> PrivacyClass:
    """The most sensitive data class this request may carry."""
    return max(
        request.constraints.allowed_privacy_classes,
        key=lambda p: list(PrivacyClass).index(p),
    )


def rank_candidates(registry: ProviderRegistry, request: ModelRequest) -> RoutingDecision:
    c = request.constraints
    strictest = _strictest_privacy(request)
    rejected: list[tuple[str, str]] = []
    defs: list = []

    for d in registry.enumerate():
        if request.preferred_provider_id and d.provider_id != request.preferred_provider_id:
            continue
        if not d.available:
            rejected.append((d.provider_id, "provider marked unavailable"))
            continue
        status = registry.status(d.provider_id)
        if not status.healthy:
            rejected.append((d.provider_id, "circuit open after consecutive failures"))
            continue
        if c.local_only and not d.local:
            rejected.append((d.provider_id, "local-only request"))
            continue
        if not c.local_only and not d.local and not c.remote_allowed:
            rejected.append((d.provider_id, "remote not allowed for this request"))
            continue
        if not d.can_handle_privacy(strictest):
            rejected.append((d.provider_id, "privacy class exceeds provider tier"))
            continue
        if _COST_ORDER[d.cost_class] > _COST_ORDER[c.max_cost_class]:
            rejected.append((d.provider_id, "cost class above request ceiling"))
            continue
        if c.require_structured_output and not d.supports_structured_output:
            rejected.append((d.provider_id, "structured output unsupported"))
            continue
        if c.require_streaming and not d.supports_streaming:
            rejected.append((d.provider_id, "streaming unsupported"))
            continue
        defs.append(d)

    if request.preferred_provider_id and not defs:
        # A pinned provider that failed compliance must NOT widen the search.
        return RoutingDecision((), tuple(rejected), pinned_unavailable=True)

    defs.sort(key=lambda d: (0 if d.local else 1, _COST_ORDER[d.cost_class], d.provider_id))
    return RoutingDecision(tuple(d.provider_id for d in defs), tuple(rejected))


class ModelRouter:
    """Executes a ModelRequest against registered providers with bounded fallback."""

    def __init__(self, registry: ProviderRegistry, providers: dict[str, ModelProvider]) -> None:
        self._registry = registry
        self._providers = providers
        missing = {d.provider_id for d in registry.enumerate()} - set(providers)
        if missing:
            raise ValueError(f"providers missing executor implementations: {sorted(missing)}")

    def route(self, request: ModelRequest, max_attempts: int = _MAX_ROUTE_ATTEMPTS) -> ModelResult:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        decision = rank_candidates(self._registry, request)
        if not decision.candidate_order:
            return ModelResult.failure(
                request.request_id,
                ErrorCategory.DEPENDENCY_UNAVAILABLE,
                "no compliant provider for request constraints"
                + (" (pinned provider unavailable)" if decision.pinned_unavailable else ""),
                retryable=False,
            )

        last_error: ModelResult | None = None
        previous_provider: str | None = None
        tried = 0
        for provider_id in decision.candidate_order[:max_attempts]:
            tried += 1
            result = self._providers[provider_id].execute(request)
            if result.ok:
                self._registry.report_success(provider_id)
                execution = result.execution
                if execution is not None and previous_provider is not None:
                    execution = replace(
                        execution,
                        fallback_from_provider_id=previous_provider,
                        fallback_reason=(
                            last_error.error.message if last_error and last_error.error else ""
                        ),
                        attempt=tried,
                    )
                    return ModelResult(
                        request_id=result.request_id,
                        ok=True,
                        content=result.content,
                        structured=result.structured,
                        chunks=result.chunks,
                        execution=execution,
                    )
                return result
            self._registry.report_failure(
                provider_id, result.error.message if result.error else ""
            )
            previous_provider = provider_id
            last_error = result
            if result.error and not result.error.retryable:
                break  # non-retryable model failure — do not loop providers

        assert last_error is not None and last_error.error is not None
        category = (
            ErrorCategory.MODEL_UNAVAILABLE
            if last_error.error.category
            in (ErrorCategory.MODEL_FAILURE, ErrorCategory.MODEL_UNAVAILABLE)
            else last_error.error.category
        )
        return ModelResult.failure(
            request.request_id,
            category,
            f"all compliant providers failed ({tried} attempts): {last_error.error.message}",
            retryable=True,
        )


__all__ = ["ModelRouter", "RoutingDecision", "rank_candidates"]

