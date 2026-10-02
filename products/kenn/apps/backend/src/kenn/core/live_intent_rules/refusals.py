"""The safety boundary: the rules that refuse before any Live action is considered.

Every other stage in the chain answers "which change was asked for". These answer
"is this a request KENN will act on at all", which is why they run first and why
no later rule is allowed to pre-empt one. A rule that reaches past a refusal and
turns it into a proposal is the worst failure this parser has, so the group stays
small and stays at the head of the chain.

Lifted verbatim out of ``live_intent._parse_request_rules``.
"""

from __future__ import annotations

from typing import Any

from kenn.core.live_intent import (
    _DESTRUCTIVE,
    _REMOVE_LOCATOR,
    _SAFETY_BYPASS,
    _UNBOUNDED_EXECUTION,
    _UNSAFE_MASTER_LEVEL,
    _UNSAFE_MASTER_MAX,
    _safety_normalised,
)


def refuse_unsafe(base: dict[str, Any], text: str) -> dict[str, Any] | None:
    """The refusal for ``text``, or None to fall through to the next stage."""
    if not text:
        base.update({"error": "A request is required.", "missing_fields": ["request"], "confidence": 1.0})
        return base
    safety_text = _safety_normalised(text)
    if _DESTRUCTIVE.search(safety_text) and _REMOVE_LOCATOR.fullmatch(text) is None:
        base.update({"mode": "refuse", "error": "Deleting, removing, overwriting, and replacing Live content are disabled by the KENN assistant boundary.", "confidence": 0.99})
        return base
    if _UNBOUNDED_EXECUTION.search(text):
        base.update({
            "mode": "refuse",
            "error": "Arbitrary code, scripts, and untyped OSC execution are outside KENN's safety boundary.",
            "confidence": 0.99,
        })
        return base
    if _SAFETY_BYPASS.search(text):
        base.update({
            "mode": "refuse",
            "error": "Requests to bypass KENN's confirmation, policy, or instruction boundary are refused.",
            "confidence": 0.99,
        })
        return base
    if _UNSAFE_MASTER_LEVEL.search(safety_text) or _UNSAFE_MASTER_MAX.search(safety_text):
        base.update({
            "mode": "refuse",
            "error": (
                "Master-track level changes are outside KENN's qualified control boundary, "
                "and I will not infer or apply a maximum output level. Nothing changed."
            ),
            "confidence": 0.99,
        })
        return base


__all__ = ["refuse_unsafe"]
