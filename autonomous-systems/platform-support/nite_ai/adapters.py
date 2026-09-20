"""Adapter layer (Phase 3).

Inversion-of-control glue between the platform and product code. A
ProductAdapter is *provided by* a product (Thursday/KENN); the platform only
sees the protocol below and never imports product modules. Adapters translate
AgentRequest -> product call -> AgentResult, preserving trace ids and
structured evidence.
"""

from __future__ import annotations

from typing import Protocol

from nite_ai.capabilities import CapabilityRegistry
from nite_ai.contracts import AgentRequest, AgentResult, CapabilityDefinition


class CapabilityHandler(Protocol):
    """Product-side implementation behind one capability id."""

    def __call__(self, request: AgentRequest) -> AgentResult: ...


class ProductAdapter:
    """Binds capability definitions to product-supplied handlers.

    The adapter performs permission checks against the request's granted
    permissions before dispatching, propagates nothing but ids to the product,
    and never inspects product internals.
    """

    def __init__(self, adapter_id: str) -> None:
        if not adapter_id:
            raise ValueError("adapter_id must not be empty")
        self.adapter_id = adapter_id
        self._handlers: dict[str, CapabilityHandler] = {}
        self._required_permissions: dict[str, tuple] = {}

    def register(
        self,
        registry: CapabilityRegistry,
        definition: CapabilityDefinition,
        handler: CapabilityHandler,
    ) -> None:
        registry.register(definition)
        self._handlers[definition.capability_id] = handler
        self._required_permissions[definition.capability_id] = definition.permissions

    def dispatch(self, request: AgentRequest) -> AgentResult:
        from nite_ai.errors import AgentError, ErrorCategory

        handler = self._handlers.get(request.capability_id)
        if handler is None:
            return AgentResult(
                request_id=request.request_id,
                status="failed",
                error=AgentError(
                    category=ErrorCategory.NOT_SUPPORTED,
                    message=f"adapter {self.adapter_id} has no handler for {request.capability_id}",
                ),
            )
        required = set(self._required_permissions.get(request.capability_id, ()))
        missing = required - set(request.granted_permissions)
        if missing:
            return AgentResult(
                request_id=request.request_id,
                status="failed",
                error=AgentError(
                    category=ErrorCategory.PERMISSION_DENIED,
                    message=f"missing granted permissions: {sorted(str(m) for m in missing)}",
                ),
            )
        result = handler(request)
        # Provenance guardrail: results must echo the originating request id.
        if result.request_id != request.request_id:
            from dataclasses import replace

            result = replace(result, request_id=request.request_id)
        return result


__all__ = ["CapabilityHandler", "ProductAdapter"]
