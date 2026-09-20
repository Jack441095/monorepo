"""Memory authority resolution for Thursday.

Not all remembered information is equally trustworthy. This module makes
the conflict order EXPLICIT and deterministic instead of leaving it to
model vibes.

Authority order (highest first):

1. AUTHORITATIVE COMPANY STATE  (nite_ai store, read fresh)
2. RECENT OWNER DECISION        (non-superseded, newest first)
3. WORKING SESSION CONTEXT      (current session facts)
4. LONG-TERM PREFERENCE         (durable user preferences — own namespace,
                                 NEVER overridden by company facts and
                                 vice versa)
5. OLD CONVERSATIONAL MEMORY    (history; stale-labelled, weakest)

Namespaces separate preference-style keys (``prefs.*``) from factual keys
(``facts.*``): a company fact can never overwrite a styling preference and
a preference can never masquerade as company truth.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class Layer(IntEnum):
    CONVERSATION = 1
    PREFERENCE = 2
    SESSION = 3
    OWNER_DECISION = 4


LAYER_NAMES = {
    Layer.CONVERSATION: "old conversational memory",
    Layer.PREFERENCE: "long-term preference",
    Layer.SESSION: "working session context",
    Layer.OWNER_DECISION: "recent owner decision",
}


@dataclass(frozen=True)
class MemoryRecord:
    layer: Layer
    key: str                 # 'facts.topic' or 'prefs.style'
    value: str
    updated_at_epoch: float
    superseded_by: str = ""  # record id of a newer decision replacing this

    @property
    def is_preference(self) -> bool:
        return self.key.startswith("prefs.")


@dataclass(frozen=True)
class Resolution:
    winner: MemoryRecord | None
    source: str              # 'company_state' or layer name
    reason: str


def resolve_conflict(
    records: list[MemoryRecord],
    *,
    company_state_value: str | None = None,
    now_epoch: float | None = None,
) -> Resolution:
    """Resolve competing memories for one factual key.

    ``company_state_value`` is what current structured company state says
    for this topic (``None`` = no authoritative data available).
    """
    now = now_epoch if now_epoch is not None else time.time()
    relevant = [r for r in records if not r.key.startswith("prefs.")]
    if not relevant:
        return Resolution(None, "none", "no records for this key")

    # Rule 1: authoritative company state beats every memory layer.
    # A memory only survives when it AGREES with current state.
    if company_state_value is not None:
        agreeing = [r for r in relevant if r.value == company_state_value]
        stale_memories = [r for r in relevant if r.value != company_state_value]
        if stale_memories:
            return Resolution(
                agreeing[0] if agreeing else None,
                "company_state",
                "company state is authoritative; conflicting memory discarded",
            )
        return Resolution(
            agreeing[0], "company_state",
            "memory agrees with current company state",
        )

    # Rule 2: among owner decisions, newest NON-SUPERSEDED wins.
    decisions = [
        r for r in relevant
        if r.layer is Layer.OWNER_DECISION and not r.superseded_by
    ]
    if decisions:
        newest = max(decisions, key=lambda r: r.updated_at_epoch)
        age = max(0.0, now - newest.updated_at_epoch)
        suffix = f" (recorded {int(age // 60)} min ago)" if age >= 60 else ""
        return Resolution(newest, LAYER_NAMES[Layer.OWNER_DECISION],
                          f"latest active owner decision{suffix}")

    # Rule 3: layer order, then recency within layer — but superseded
    # records are dead everywhere, not just within the decision layer.
    live = [r for r in relevant if not r.superseded_by]
    if not live:
        return Resolution(None, "none", "all records superseded")

    def sort_key(r: MemoryRecord):
        return (-r.layer, -r.updated_at_epoch)

    winner = sorted(live, key=sort_key)[0]
    age = max(0.0, now - winner.updated_at_epoch)
    staleness = ""
    if age > 24 * 3600:
        staleness = f" [stale: from {int(age // 86400)}d ago]"
    return Resolution(
        winner,
        LAYER_NAMES[winner.layer],
        f"resolved by layer order then recency{staleness}",
    )


def resolve_preference(records: list[MemoryRecord]) -> Resolution:
    """Preferences resolve ONLY against other preferences."""
    prefs = [r for r in records if r.is_preference]
    if not prefs:
        return Resolution(None, "none", "no preference recorded")
    newest = max(prefs, key=lambda r: r.updated_at_epoch)
    return Resolution(
        newest, LAYER_NAMES[Layer.PREFERENCE],
        "newest preference wins; company state does not govern style",
    )


def validate_memory_write(record: MemoryRecord) -> bool:
    """Write policy: typed namespace, non-empty bounded value.

    Arbitrary model output must not become persistent memory unchecked.
    """
    if not record.key or "." not in record.key:
        return False
    namespace = record.key.split(".", 1)[0]
    if namespace not in ("facts", "prefs"):
        return False
    if len(record.value) > 500:
        return False
    if record.updated_at_epoch <= 0:
        return False
    return True


def freshness_label(record: MemoryRecord, *, now_epoch: float | None = None) -> str:
    now = now_epoch if now_epoch is not None else time.time()
    age = max(0.0, now - record.updated_at_epoch)
    if age < 3600:
        return "fresh"
    if age < 7 * 86400:
        return "recent"
    return "stale"


__all__ = [
    "Layer",
    "MemoryRecord",
    "Resolution",
    "resolve_conflict",
    "resolve_preference",
    "validate_memory_write",
    "freshness_label",
]
