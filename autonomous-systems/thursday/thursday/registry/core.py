"""Service registry core: ServiceDef, permission scoping, trigger scoring.

Split out of thursday/registry.py (was 1,263 lines) — see docs/BACKLOG.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Callable

# PermissionScope is a small, stable, 5-value vocabulary vendored locally
# (needed as a dataclass field default below, at import time). Capability is
# NOT vendored -- it's a validated, schema-versioned contract object shared
# with Audio_Too's own registry; a second, independently-maintained copy
# would risk silently drifting from the real schema. It stays a real,
# lazily-imported integration point -- see docs/EXTRACTION_COUPLING.md.
from thursday._compat import PermissionScope


class CapabilityContractUnavailable(RuntimeError):
    """Raised when audio_too's Capability contract type isn't installed.

    Thursday's own ServiceDef/registry works standalone; only the typed
    Capability conversion (ServiceDef.to_capability) needs audio_too.
    """


def _capability_cls():
    try:
        from audio_too import Capability
    except ImportError as exc:
        raise CapabilityContractUnavailable(
            "ServiceDef.to_capability() requires the audio_too package "
            f"(not installed): {exc}"
        ) from exc
    return Capability


class ActionRisk(str, Enum):
    """Maximum consequence of a service or concrete service request."""

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
class ServiceDef:
    """Declarative service definition."""

    name: str
    description: str
    examples: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)
    requires_context: list[str] = field(default_factory=list)
    action: Callable = lambda ctx, api, text: ""
    post_process: Callable | None = None
    version: str = "1.0.0"
    permissions: tuple[PermissionScope, ...] = (PermissionScope.READ,)
    risk: ActionRisk = ActionRisk.READ_ONLY
    resource_needs: dict = field(default_factory=dict)

    def to_capability(self, service_id: str) -> "Capability":
        Capability = _capability_cls()
        return Capability(
            name=f"thursday.{service_id}",
            version=self.version,
            description=self.description,
            permissions=self.permissions,
            input_schema={
                "type": "object",
                "required": ["text", "context"],
                "properties": {
                    "text": {"type": "string"},
                    "context": {"type": "object"},
                },
            },
            output_schema={
                "type": "object",
                "required": ["value"],
                "properties": {"value": {}},
            },
            resource_needs=self.resource_needs,
        )

    def to_dict(self, service_id: str = "") -> dict:
        capability = self.to_capability(service_id).to_dict() if service_id else None
        return {
            "name": self.name,
            "description": self.description,
            "examples": self.examples,
            "triggers": self.triggers,
            "intents": self.intents,
            "requires_context": self.requires_context,
            "risk": self.risk.value,
            "confirmation_required": self.risk.requires_confirmation,
            "capability": capability,
        }


_ANALYSIS_SERVICES = {
    "kenn",
    "audio_analysis",
    "mix_review",
    "mix_review_detail",
    "mix_review_timeline",
    "mix_review_version_diff",
    "kenn_review_handoff",
    "kenn_compare",
    "codebase_test",
}
_PROPOSAL_SERVICES = {"admin_agent", "marketing_agent", "research_agent", "business_insights"}
_MUTATION_SERVICES = {
    "audiogen",
    "snapshot",
    "daily_maintenance",
    "weekly_maintenance",
    "audiogen_render",
    "audiogen_job",
    "mix_review_correction_rack",
    "creative_lab_repairs",
    "reminder_set",
    "user_profile_prefs",
    "kenn_save_note",
    "agent_workflow_chain",
    "ableton_push",
    "sessions",
    "expenses",
    "invoices",
    "drafts",
    "admin_agent",
    "marketing_agent",
    "codebase_edit",
    "codebase_git",
    "codebase_build",
}

_EXTERNAL_SERVICES = {"drafts", "admin_agent", "marketing_agent"}


def _service_risk(service_id: str) -> ActionRisk:
    """Return a service's maximum declared risk for capability discovery."""
    if service_id in _EXTERNAL_SERVICES:
        return ActionRisk.EXTERNAL_COMMUNICATION
    if service_id in _MUTATION_SERVICES:
        return ActionRisk.LOCAL_MUTATION
    if service_id in _ANALYSIS_SERVICES:
        return ActionRisk.ANALYSIS
    if service_id in _PROPOSAL_SERVICES:
        return ActionRisk.PROPOSAL
    return ActionRisk.READ_ONLY


def _permission_scopes(service_id: str) -> tuple[PermissionScope, ...]:
    scopes = [PermissionScope.READ]
    if service_id in _ANALYSIS_SERVICES:
        scopes.append(PermissionScope.ANALYZE)
    if service_id in _PROPOSAL_SERVICES:
        scopes.append(PermissionScope.PROPOSE)
    if service_id in _MUTATION_SERVICES:
        scopes.append(PermissionScope.MUTATE_LOCAL)
    if service_id in _EXTERNAL_SERVICES:
        scopes.append(PermissionScope.COMMUNICATE_EXTERNAL)
    return tuple(scopes)


def request_risk(service_id: str, text: str) -> ActionRisk:
    """Classify the concrete operation, including mixed read/write services.

    The rules are intentionally explicit and service-scoped. A generic keyword
    matcher is unsafe because words such as "send" and "set" have different
    consequences in different handlers.
    """
    lower = text.casefold()

    if service_id == "audiogen_job":
        return (
            ActionRisk.LOCAL_MUTATION
            if any(word in lower for word in ("cancel", "stop", "retry"))
            else ActionRisk.READ_ONLY
        )
    if service_id == "user_profile_prefs":
        mutators = ("create shortcut", "add shortcut", "remove shortcut", "delete shortcut", "update", "set ")
        return ActionRisk.LOCAL_MUTATION if any(word in lower for word in mutators) else ActionRisk.READ_ONLY
    if service_id == "sessions":
        mutators = ("schedule", "book", "create", "new session", "add session")
        return ActionRisk.LOCAL_MUTATION if any(word in lower for word in mutators) else ActionRisk.READ_ONLY
    if service_id == "expenses":
        mutators = ("add", "record", "log", "new expense")
        return ActionRisk.LOCAL_MUTATION if any(word in lower for word in mutators) else ActionRisk.READ_ONLY
    if service_id == "invoices":
        return ActionRisk.LOCAL_MUTATION if any(word in lower for word in ("pdf", "generate")) else ActionRisk.READ_ONLY
    if service_id == "drafts":
        read_only = any(word in lower for word in ("pending", "unsent", "list", "show"))
        return ActionRisk.READ_ONLY if read_only else ActionRisk.EXTERNAL_COMMUNICATION
    if service_id == "admin_agent":
        if re.search(r"\b(?:send|email)\b.*\binvoice\b", lower):
            return ActionRisk.EXTERNAL_COMMUNICATION
        if any(word in lower for word in ("create invoice", "make invoice", "new project", "create project", "add project", "new client", "create client", "add client", "add customer")):
            return ActionRisk.LOCAL_MUTATION
        return ActionRisk.PROPOSAL
    if service_id == "marketing_agent":
        if any(word in lower for word in ("publish", "send campaign", "run campaign", "run a campaign")):
            return ActionRisk.EXTERNAL_COMMUNICATION
        if any(word in lower for word in ("new lead", "add lead", "create lead", "save lead")):
            return ActionRisk.LOCAL_MUTATION
        return ActionRisk.PROPOSAL
    if service_id == "creative_lab_repairs":
        mutators = ("create", "artifact", "promote", "export", "run repair")
        return ActionRisk.LOCAL_MUTATION if any(word in lower for word in mutators) else ActionRisk.READ_ONLY
    if service_id == "codebase_git":
        if any(word in lower for word in ("push --force", "push -f", "force push")):
            return ActionRisk.DESTRUCTIVE
        return ActionRisk.LOCAL_MUTATION
    if service_id == "codebase_edit":
        return ActionRisk.LOCAL_MUTATION
    if service_id == "codebase_build":
        return ActionRisk.LOCAL_MUTATION

    return _service_risk(service_id)


# ─── Helper: trigger-based scoring ───────────────────────────────────────


def score_by_triggers(text: str, triggers: list[str]) -> float:
    """Score text against a list of trigger phrases.

    Gives higher weight to longer/phrased matches.
    """
    text_lower = text.lower()
    text_words = set(text_lower.split())
    score = 0.0
    for trigger in triggers:
        trigger_words = trigger.split()
        if len(trigger_words) == 1:
            if trigger in text_words:
                score += 1.0
        else:
            if trigger in text_lower:
                score += len(trigger_words) ** 2
            elif all(w in text_words for w in trigger_words):
                score += 1.0
    return score
