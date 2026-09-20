"""Temporal company truth for Thursday V2-I.

An observation that was true on Day 3 must not automatically remain
authoritative on Day 25. This module records facts with explicit
provenance and validity so long-horizon reasoning can distinguish:

    CURRENT     newest trusted observation for a key
    HISTORICAL  superseded by a newer observation (history preserved)
    STALE       current observation older than the key's freshness TTL
    CONFLICTED  two different values observed at the same logical tick
    INVALID     fact retracted by its source or provenance rejected

Design rules
------------
* History is never erased when newer truth arrives — old facts become
  HISTORICAL with ``superseded_by`` set.
* ``authoritative_value`` fails closed: a STALE-beyond-TTL or CONFLICTED
  key yields no value rather than a convenient guess.
* Facts are inert data. A historical fact NEVER grants authority
  (approvals/permissions live in integration_models / owner_decisions).

Time is supplied by an injected Clock (V2-I requirement) — never read
from wall time inside this module.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from thursday.simulated_clock import ClockProtocol


class FactStatus(str, Enum):
    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"
    INVALID = "INVALID"
    CONFLICTED = "CONFLICTED"


@dataclass(frozen=True)
class Fact:
    """A single observed fact with provenance.

    fact → source → observed_at → validity → superseded_by
    """

    fact_id: str
    key: str
    value: str
    source: str                 # e.g. "observer:sandbox", "report:company"
    observed_at_epoch: float
    content_digest: str         # sha256 of key+value — identity of meaning
    status: str = FactStatus.CURRENT.value
    superseded_by: str = ""     # fact_id of the replacing fact
    invalidated_reason: str = ""

    def matches(self, value: str) -> bool:
        return self.value == value


def _digest(key: str, value: str) -> str:
    payload = json.dumps({"key": key, "value": value}, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class TemporalStore:
    """Bounded store of temporal facts keyed by topic.

    Parameters
    ----------
    clock : ClockProtocol
        Injected time source.
    default_ttl_seconds : float
        Freshness window after which a CURRENT fact reads as STALE.
        Per-key TTLs override this via ``ttl_overrides``.
    max_history_per_key : int
        Oldest HISTORICAL facts beyond this count are dropped during
        compaction (provenance classes that must never be compacted are
        handled by state_compaction, not here).
    """

    clock: ClockProtocol
    default_ttl_seconds: float = 3 * 86400.0
    ttl_overrides: dict[str, float] = field(default_factory=dict)
    max_history_per_key: int = 32

    # key → [Fact, ...] append-ordered oldest→newest
    _facts: dict[str, list[Fact]] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Writing observations
    # ------------------------------------------------------------------

    def observe(self, key: str, value: str, *, source: str,
                observed_at: float | None = None) -> tuple[Fact, bool]:
        """Record an observation for ``key``.

        Returns ``(fact, changed)`` where ``changed`` indicates whether
        this observation differs from the previous CURRENT value.

        Same-tick contradiction from a *different* source marks the key
        CONFLICTED (both values retained; nothing silently chosen).
        """
        at = self.clock.now() if observed_at is None else float(observed_at)
        history = self._facts.setdefault(key, [])
        digest = _digest(key, value)

        # Contradiction detection: another source already observed a
        # DIFFERENT value at exactly this tick.
        for existing in reversed(history):
            if existing.observed_at_epoch == at and existing.source != source \
                    and existing.content_digest != digest \
                    and existing.status == FactStatus.CURRENT.value:
                conflicting = Fact(
                    fact_id=uuid.uuid4().hex, key=key, value=value,
                    source=source, observed_at_epoch=at, content_digest=digest,
                    status=FactStatus.CONFLICTED.value,
                )
                history.append(conflicting)
                return conflicting, True

        changed = True
        if history:
            prev = history[-1]
            if prev.content_digest == digest and prev.status == FactStatus.CURRENT.value:
                # Repeated equivalent observation — deduplicate the event
                # but refresh last-seen via a lightweight record.
                refreshed = Fact(
                    fact_id=uuid.uuid4().hex, key=key, value=value,
                    source=source, observed_at_epoch=at, content_digest=digest,
                    status=FactStatus.CURRENT.value,
                )
                if prev.status == FactStatus.CURRENT.value and len(history) > 1:
                    pass   # prior identical record stays as history
                history.append(refreshed)
                return refreshed, False
            # Supersede the previous current fact.
            prev_idx = len(history) - 1
            new_fact = Fact(
                fact_id=uuid.uuid4().hex, key=key, value=value,
                source=source, observed_at_epoch=at, content_digest=digest,
            )
            prev_status = (
                FactStatus.HISTORICAL.value
                if prev.status == FactStatus.CURRENT.value else prev.status
            )
            history[prev_idx] = Fact(
                fact_id=prev.fact_id, key=prev.key, value=prev.value,
                source=prev.source, observed_at_epoch=prev.observed_at_epoch,
                content_digest=prev.content_digest, status=prev_status,
                superseded_by=new_fact.fact_id,
            )
            history.append(new_fact)
            return new_fact, True

        first = Fact(
            fact_id=uuid.uuid4().hex, key=key, value=value,
            source=source, observed_at_epoch=at, content_digest=digest,
        )
        history.append(first)
        return first, True

    def invalidate(self, key: str, reason: str) -> bool:
        """Retract the current fact for a key (source retraction)."""
        history = self._facts.get(key)
        if not history:
            return False
        cur = history[-1]
        if cur.status != FactStatus.CURRENT.value:
            return False
        history[-1] = Fact(
            fact_id=cur.fact_id, key=cur.key, value=cur.value,
            source=cur.source, observed_at_epoch=cur.observed_at_epoch,
            content_digest=cur.content_digest, status=FactStatus.INVALID.value,
            invalidated_reason=reason,
        )
        return True

    # ------------------------------------------------------------------
    # Reading truth (fail closed)
    # ------------------------------------------------------------------

    def ttl_for(self, key: str) -> float:
        return self.ttl_overrides.get(key, self.default_ttl_seconds)

    def status_of(self, key: str) -> str | None:
        history = self._facts.get(key)
        if not history:
            return None
        cur = history[-1]
        if cur.status == FactStatus.CONFLICTED.value:
            return FactStatus.CONFLICTED.value
        if cur.status == FactStatus.INVALID.value:
            return FactStatus.INVALID.value
        if cur.status == FactStatus.SUPERSEDED.value:
            return FactStatus.SUPERSEDED.value
        if self.clock.now() - cur.observed_at_epoch > self.ttl_for(key):
            return FactStatus.STALE.value
        return FactStatus.CURRENT.value

    def current_fact(self, key: str) -> Fact | None:
        """Newest fact regardless of staleness (inspection only)."""
        history = self._facts.get(key)
        return history[-1] if history else None

    def authoritative_value(self, key: str) -> tuple[bool, str]:
        """Return ``(ok, value)`` — fails closed on anything but CURRENT.

        STALE / CONFLICTED / INVALID / missing keys yield ``(False, "")``.
        Trust-sensitive callers MUST treat ``ok=False`` as "no authority".
        """
        st = self.status_of(key)
        if st != FactStatus.CURRENT.value:
            return False, ""
        return True, self.current_fact(key).value

    def history(self, key: str) -> list[Fact]:
        return list(self._facts.get(key, ()))

    # ------------------------------------------------------------------
    # Compaction support
    # ------------------------------------------------------------------

    def compact_history(self, keep: int | None = None) -> int:
        """Drop oldest HISTORICAL facts beyond retention; return removed."""
        limit = self.max_history_per_key if keep is None else keep
        removed = 0
        for key, history in list(self._facts.items()):
            terminal_or_current = [
                f for f in history
                if f.status in (FactStatus.CURRENT.value, FactStatus.CONFLICTED.value)
            ]
            historical = [
                f for f in history
                if f.status not in (FactStatus.CURRENT.value, FactStatus.CONFLICTED.value)
            ]
            excess = max(0, len(historical) - limit)
            if excess:
                kept_hist = historical[excess:]
                self._facts[key] = kept_hist + terminal_or_current
                removed += excess
        return removed

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_state(self) -> dict[str, Any]:
        return {
            "default_ttl_seconds": self.default_ttl_seconds,
            "max_history_per_key": self.max_history_per_key,
            "facts": {
                k: [f.__dict__ for f in v] for k, v in self._facts.items()
            },
        }

    @classmethod
    def from_state(cls, state: dict[str, Any], clock: ClockProtocol) -> "TemporalStore":
        store = cls(
            clock=clock,
            default_ttl_seconds=state.get("default_ttl_seconds", 3 * 86400.0),
            max_history_per_key=state.get("max_history_per_key", 32),
        )
        for key, raw in state.get("facts", {}).items():
            store._facts[key] = [Fact(**r) for r in raw]
        return store


__all__ = ["Fact", "FactStatus", "TemporalStore"]
