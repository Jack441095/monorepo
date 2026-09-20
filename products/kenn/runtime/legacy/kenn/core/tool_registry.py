"""Audio-domain tool-call registry (Phase 3 of
docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md).

Mirrors Thursday's ServiceDef/ActionRisk shape (thursday/registry/core.py)
deliberately -- this is the same pattern applied to KENN's own audio tools
(stem separation, mix review, AutoMix, DAW moves), not a second, competing
confirmation mechanism. Reuses thursday.confirmation's signed-token
primitives directly (issue_confirmation/verify_confirmation are already
generic -- session_id/service_id/text, no Thursday-internal state), rather
than reimplementing token issuance.

READ_ONLY/ANALYSIS/PROPOSAL tools run immediately, no gate -- this covers
most of "help make mix decisions" day to day (run a review, compare a
reference, separate stems, render an AutoMix pass: all produce new derived
output, nothing pre-existing is overwritten). LOCAL_MUTATION/
EXTERNAL_COMMUNICATION/DESTRUCTIVE tools require a valid confirmation token,
matching Thursday's own risk tiers exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from nite_core.confirmation import issue_confirmation, verify_confirmation


class ActionRisk(str, Enum):
    """Maximum consequence of a tool call. Mirrors thursday/registry/core.py's
    ActionRisk exactly -- same tiers, same meaning, one confirmation
    mechanism across both systems."""

    READ_ONLY = "read_only"
    ANALYSIS = "analysis"
    PROPOSAL = "proposal"
    LOCAL_MUTATION = "local_mutation"
    EXTERNAL_COMMUNICATION = "external_communication"
    DESTRUCTIVE = "destructive"

    @property
    def requires_confirmation(self) -> bool:
        return self in {
            ActionRisk.LOCAL_MUTATION,
            ActionRisk.EXTERNAL_COMMUNICATION,
            ActionRisk.DESTRUCTIVE,
        }


@dataclass
class ToolDef:
    """Declarative tool definition. handler receives only the caller's
    kwargs (not session_id/confirm_token -- those are the registry's own
    concern, kept out of individual handlers)."""

    name: str
    description: str
    risk: ActionRisk
    handler: Callable[..., dict]


_REGISTRY: dict[str, ToolDef] = {}


def register(tool: ToolDef) -> None:
    _REGISTRY[tool.name] = tool


def get_tool(name: str) -> ToolDef | None:
    return _REGISTRY.get(name)


def list_tools() -> list[dict]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "risk": tool.risk.value,
            "confirmation_required": tool.risk.requires_confirmation,
        }
        for tool in _REGISTRY.values()
    ]


def _request_text(name: str, kwargs: dict) -> str:
    """Deterministic text to bind into the confirmation signature -- must be
    identical between the issuing call and the confirming call, or the
    signature won't match (by design: confirming a DIFFERENT request than
    the one shown to the user should fail)."""
    return f"{name}:" + ",".join(f"{k}={kwargs[k]!r}" for k in sorted(kwargs))


def invoke_tool(name: str, *, session_id: str, confirm_token: str = "", **kwargs) -> dict:
    """Execute a registered tool, gating LOCAL_MUTATION+ tools behind a
    confirmation token. Returns the handler's own {ok, ...} dict for
    ungated tools; for gated tools without (or with an invalid/expired)
    confirm_token, returns {ok: False, confirmation_required: True,
    confirm_token, message} instead of executing -- the caller must show
    that message to the user and re-invoke with the returned token."""
    tool = get_tool(name)
    if tool is None:
        return {"ok": False, "error": f"Unknown tool: {name!r}"}

    if not tool.risk.requires_confirmation:
        return tool.handler(**kwargs)

    text = _request_text(name, kwargs)
    if confirm_token:
        if verify_confirmation(confirm_token, session_id=session_id, service_id=name, text=text):
            return tool.handler(**kwargs)
        return {"ok": False, "error": "Invalid or expired confirmation token."}

    token, _ = issue_confirmation(session_id=session_id, service_id=name, text=text)
    return {
        "ok": False,
        "confirmation_required": True,
        "confirm_token": token,
        "message": f"This will {tool.description[0].lower()}{tool.description[1:]}. "
        f"Reply 'confirm {token}' to proceed.",
    }
