"""Context primitives and budgeting (Phase 4A).

Typed context *references* plus a deterministic budget-based selector.
No context database, no persistence — references point into product-owned
stores. Priority order: request > task state > evidence > product context >
retrieved memory > historical summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nite_ai._serialization import dataclass_to_dict
from nite_ai.errors import ValidationError
from nite_ai.permissions import PrivacyClass


class ContextLayer(str, Enum):
    REQUEST = "request"                 # always included
    TASK_STATE = "task_state"
    EVIDENCE = "evidence"
    PRODUCT_CONTEXT = "product_context"
    RETRIEVED_MEMORY = "retrieved_memory"
    HISTORY_SUMMARY = "history_summary"


_LAYER_PRIORITY = {layer: i for i, layer in enumerate(ContextLayer)}


@dataclass(frozen=True)
class ContextRef:
    """A typed reference into a product-owned context store."""

    layer: ContextLayer
    ref_id: str
    estimated_tokens: int = 0
    privacy_class: PrivacyClass = PrivacyClass.USER_TEXT
    payload: dict[str, Any] | None = None   # inline only for tiny REQUEST-layer data

    def __post_init__(self) -> None:
        if not self.ref_id:
            raise ValidationError("ContextRef.ref_id must not be empty")
        if self.estimated_tokens < 0:
            raise ValidationError("ContextRef.estimated_tokens must be non-negative")
        if self.payload is not None and self.layer is not ContextLayer.REQUEST:
            raise ValidationError(
                "inline payloads are allowed only for the REQUEST layer; "
                "all other layers must reference external stores"
            )
        if self.payload is not None and self.privacy_class is PrivacyClass.SECRET:
            raise ValidationError("SECRET data may not be inlined in a ContextRef")


@dataclass(frozen=True)
class ContextBudget:
    max_total_tokens: int
    layer_caps: dict[ContextLayer, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_total_tokens <= 0:
            raise ValidationError("ContextBudget.max_total_tokens must be > 0")
        for layer, cap in self.layer_caps.items():
            if cap < 0:
                raise ValidationError(f"layer cap for {layer} must be non-negative")


def select_context(refs: tuple[ContextRef, ...], budget: ContextBudget) -> tuple[ContextRef, ...]:
    """Deterministically select refs within budget by layer priority, then
    cheapest-first within a layer. REQUEST layer is always kept (inline)."""
    ordered = sorted(refs, key=lambda r: (_LAYER_PRIORITY[r.layer], r.estimated_tokens, r.ref_id))
    selected: list[ContextRef] = []
    used = 0
    layer_used: dict[ContextLayer, int] = {}
    for ref in ordered:
        cap = budget.layer_caps.get(ref.layer)
        if cap is not None and layer_used.get(ref.layer, 0) + ref.estimated_tokens > cap:
            continue
        if used + ref.estimated_tokens > budget.max_total_tokens:
            continue
        selected.append(ref)
        used += ref.estimated_tokens
        layer_used[ref.layer] = layer_used.get(ref.layer, 0) + ref.estimated_tokens
    return tuple(selected)


@dataclass(frozen=True)
class ContextEnvelope:
    """The bounded context handed to one execution."""

    request_ref: ContextRef
    included_refs: tuple[ContextRef, ...] = ()
    total_estimated_tokens: int = 0

    def to_dict(self) -> dict:
        return dataclass_to_dict(self)


def build_envelope(refs: tuple[ContextRef, ...], budget: ContextBudget) -> ContextEnvelope:
    request_refs = [r for r in refs if r.layer is ContextLayer.REQUEST]
    if not request_refs:
        raise ValidationError("ContextEnvelope requires at least one REQUEST-layer ref")
    selected = select_context(refs, budget)
    return ContextEnvelope(
        request_ref=request_refs[0],
        included_refs=selected,
        total_estimated_tokens=sum(r.estimated_tokens for r in selected),
    )


__all__ = [
    "ContextBudget",
    "ContextEnvelope",
    "ContextLayer",
    "ContextRef",
    "build_envelope",
    "select_context",
]
