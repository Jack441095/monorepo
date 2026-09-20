"""Deterministic proactivity classification for company events.

A useful assistant must know when NOT to interrupt. This module classifies
company events into explicit attention classes using rule-grounded features
— never raw LLM judgement, and never urgency claimed inside untrusted text.

Classes (escalating):
    IGNORE          not worth recording as an alert
    LOG_ONLY        record for later retrieval, never surfaces
    WEEKLY_REVIEW   batch into the weekly review digest
    NEXT_BRIEF      include in the next daily brief
    SURFACE_SOON    surface at the next natural opportunity
    INTERRUPT_NOW   break through immediately (rare)

Grounding rules:
- Urgency comes from STRUCTURED fields (severity/kind), never from text
  content inside task titles or descriptions — those are data (§65).
- Duplicate detection downgrades repeats so unchanged state cannot nag.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class AttentionClass(str, Enum):
    INTERRUPT_NOW = "interrupt_now"
    SURFACE_SOON = "surface_soon"
    NEXT_BRIEF = "next_brief"
    WEEKLY_REVIEW = "weekly_review"
    LOG_ONLY = "log_only"
    IGNORE = "ignore"


_CLASS_ORDER = {
    AttentionClass.IGNORE: 0,
    AttentionClass.LOG_ONLY: 1,
    AttentionClass.WEEKLY_REVIEW: 2,
    AttentionClass.NEXT_BRIEF: 3,
    AttentionClass.SURFACE_SOON: 4,
    AttentionClass.INTERRUPT_NOW: 5,
}

_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


@dataclass(frozen=True)
class CompanyEvent:
    """One structured company event awaiting an attention decision.

    ``text`` fields are DATA ONLY — they may never raise classification.
    """

    event_id: str
    kind: str  # security|release_blocker|deployment_failure|approval_needed|
    # task_overdue|agent_failure|completion|metric_change|doc_issue|
    # blocker_resolved|risk_update|invoice_due|routine_success
    severity: str = "medium"  # critical|high|medium|low|info
    owner_action_required: bool = False
    reversible: bool = True
    deadline_epoch: float | None = None
    subject: str = ""  # dedup identity component
    first_occurrence: bool = True  # False when seen recently (duplicate)


@dataclass(frozen=True)
class ProactiveDecision:
    event_id: str
    event_class: AttentionClass
    reason: str
    suppressed_duplicate: bool = False


def _downgrade(cls: AttentionClass) -> AttentionClass:
    order = max(0, _CLASS_ORDER[cls] - 1)
    for candidate, value in _CLASS_ORDER.items():
        if value == order:
            return candidate
    return AttentionClass.LOG_ONLY


def classify_event(
    event: CompanyEvent,
    *,
    now_epoch: float | None = None,
    duplicate_window_s: float = 6 * 3600.0,
) -> ProactiveDecision:
    """Rule-grounded attention classification. Fully deterministic."""
    import time as time_module

    now = time_module.time() if now_epoch is None else now_epoch
    severity_rank = _SEVERITY_RANK.get(event.severity, 2)
    suppressed = False
    base_cls: AttentionClass | None = None
    reason = ""

    kind = event.kind

    if kind == "security":
        if severity_rank >= 3:
            base_cls = AttentionClass.INTERRUPT_NOW
            reason = f"security issue with {event.severity} severity"
        else:
            base_cls = AttentionClass.SURFACE_SOON
            reason = "minor security signal"

    elif kind in ("deployment_failure", "release_blocker"):
        if severity_rank >= 3 and event.owner_action_required:
            base_cls = AttentionClass.INTERRUPT_NOW
            reason = f"{kind} requiring owner action"
        elif severity_rank >= 3:
            base_cls = AttentionClass.SURFACE_SOON
            reason = f"{kind} being auto-handled"
        else:
            base_cls = AttentionClass.NEXT_BRIEF
            reason = f"low-severity {kind}"

    elif kind == "approval_needed":
        if event.reversible and severity_rank <= 2:
            base_cls = AttentionClass.NEXT_BRIEF
            reason = "reversible low-risk approval can wait for the brief"
        else:
            base_cls = AttentionClass.SURFACE_SOON
            reason = "irreversible or high-risk approval pending"

    elif kind == "task_overdue":
        overdue_hours = (
            max(0.0, now - event.deadline_epoch) / 3600.0
            if event.deadline_epoch
            else 0.0
        )
        if severity_rank >= 3 and overdue_hours >= 24:
            base_cls = AttentionClass.SURFACE_SOON
            reason = "high-priority task over a day late"
        else:
            base_cls = AttentionClass.NEXT_BRIEF
            reason = "overdue task scheduled for brief"

    elif kind == "agent_failure":
        # Only an UNRECOVERABLE failure at CRITICAL severity pages the owner;
        # high-severity recoverable-in-principle failures surface soon.
        if event.reversible is False and severity_rank >= 4:
            base_cls = AttentionClass.INTERRUPT_NOW
            reason = "unrecoverable agent failure at critical severity"
        else:
            base_cls = AttentionClass.SURFACE_SOON
            reason = "agent failure surfaced soon"

    elif kind == "blocker_resolved":
        base_cls = AttentionClass.LOG_ONLY
        reason = "resolved state needs confirmation only"

    elif kind == "invoice_due":
        if event.deadline_epoch is not None and event.deadline_epoch - now < 86400:
            base_cls = AttentionClass.SURFACE_SOON
            reason = "invoice due within 24h"
        else:
            base_cls = AttentionClass.NEXT_BRIEF
            reason = "upcoming invoice included in brief"

    elif kind == "goal_offtrack":
        if severity_rank >= 3:
            base_cls = AttentionClass.SURFACE_SOON
            reason = "goal moved off track"
        else:
            base_cls = AttentionClass.NEXT_BRIEF
            reason = "minor goal drift noted in brief"

    elif kind == "invoice_overdue":
        if severity_rank >= 3:
            base_cls = AttentionClass.SURFACE_SOON
            reason = "overdue invoice needs chasing"
        else:
            base_cls = AttentionClass.NEXT_BRIEF
            reason = "overdue invoice batched into brief"

    elif kind == "payment_failed":
        if event.owner_action_required and severity_rank >= 3:
            base_cls = AttentionClass.INTERRUPT_NOW
            reason = "failed payment requiring owner action"
        else:
            base_cls = AttentionClass.SURFACE_SOON
            reason = "payment failure surfaced soon"

    elif kind == "expense_flag":
        base_cls = AttentionClass.NEXT_BRIEF
        reason = "flagged expense for brief review"

    elif kind == "ticket_sla_breach":
        if severity_rank >= 3:
            base_cls = AttentionClass.SURFACE_SOON
            reason = "support SLA breach"
        else:
            base_cls = AttentionClass.NEXT_BRIEF
            reason = "minor SLA slip in brief"

    elif kind in ("risk_update", "milestone"):
        base_cls = AttentionClass.NEXT_BRIEF
        reason = f"{kind} batched into brief"

    elif kind == "doc_issue":
        base_cls = AttentionClass.LOG_ONLY
        reason = "documentation nit does not interrupt"

    elif kind == "metric_change":
        base_cls = AttentionClass.WEEKLY_REVIEW
        reason = "routine metric movement reviewed weekly"

    elif kind in ("completion", "routine_success"):
        base_cls = AttentionClass.LOG_ONLY
        reason = "successful routine work logged silently"

    else:
        base_cls = AttentionClass.LOG_ONLY
        reason = f"unknown kind '{kind}' defaults to log-only (fail quiet)"

    # Duplicate suppression: repeated unchanged state downgrades one level;
    # it may never UPGRADE.
    if not event.first_occurrence:
        base_cls = _downgrade(base_cls)
        suppressed = True
        reason = f"duplicate of recent '{event.subject or kind}' — downgraded"

    return ProactiveDecision(
        event_id=event.event_id,
        event_class=base_cls,
        reason=reason,
        suppressed_duplicate=suppressed,
    )


__all__ = ["AttentionClass", "CompanyEvent", "ProactiveDecision", "classify_event"]
