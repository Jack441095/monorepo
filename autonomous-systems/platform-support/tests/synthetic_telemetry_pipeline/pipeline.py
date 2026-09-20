"""Local store, consent-gated exporter, aggregator, retention, collector."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from synthetic_telemetry_pipeline.catalog import PrivacyLevel
from synthetic_telemetry_pipeline.envelope import (
    Envelope,
    TelemetryViolation,
    envelope_to_wire,
    validate_envelope_dict,
)

LOCAL_MAX_AGE_DAYS = 30
K_ANONYMITY_MIN_SESSIONS = 5


@dataclass(frozen=True)
class ConsentState:
    usage_metrics: bool = False
    diagnostics: bool = False
    improve_classification: bool = False


class SessionManager:
    """Rotating pseudonymous session identity (clock injectable for determinism)."""

    ROTATE_AFTER = timedelta(hours=24)

    def __init__(self, started_at: datetime | None = None) -> None:
        self._started = started_at or datetime.now(UTC)
        self.session_id = self._new_id(self._started)

    @staticmethod
    def _new_id(when: datetime) -> str:
        return hashlib.sha256(when.isoformat().encode()).hexdigest()[:32]

    def current(self, now: datetime | None = None) -> str:
        now = now or datetime.now(UTC)
        if now - self._started >= self.ROTATE_AFTER:
            return self.rotate(now=now)
        return self.session_id

    def rotate(self, now: datetime | None = None) -> str:
        now = now or datetime.now(UTC)
        self.session_id = self._new_id(now)
        self._started = now
        return self.session_id


class LocalStore:
    """Append-only local NDJSON buffer; user-visible and user-erasable in production."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def append(self, env: Envelope) -> None:
        self.events.append(envelope_to_wire(env))

    def erase(self) -> None:
        self.events.clear()


def trim_store(store: LocalStore, now: datetime, max_events: int = 1000) -> int:
    cutoff = now - timedelta(days=LOCAL_MAX_AGE_DAYS)
    kept: list[dict] = []
    removed = 0
    for event in store.events:
        ts = datetime.fromisoformat(event["timestamp"])
        if ts >= cutoff:
            kept.append(event)
        else:
            removed += 1
    overflow = max(0, len(kept) - max_events)
    removed += overflow
    store.events = kept[overflow:]
    return removed


class DailyAggregator:
    """L1 rollup keyed by (day, action, outcome, feature_version), deduped by event_id."""

    def __init__(self) -> None:
        self.counts: dict[tuple[str, str, str, str], int] = {}
        self._seen: set[str] = set()

    def add(self, env: Envelope) -> bool:
        if env.event_id in self._seen:
            return False
        self._seen.add(env.event_id)
        day = env.timestamp[:10]
        key = (day, env.action, env.outcome, env.feature_version)
        self.counts[key] = self.counts.get(key, 0) + 1
        return True

    @property
    def total(self) -> int:
        return sum(self.counts.values())


class BatchExporter:
    """Consent gate. With every toggle OFF this provably emits nothing."""

    def export(self, store: LocalStore, consent: ConsentState) -> list[str]:
        if not (consent.usage_metrics or consent.diagnostics):
            return []
        batches: list[str] = []
        current: list[dict] = []
        for event in store.events:
            level = event["privacy_level"]
            if level == PrivacyLevel.L3.value and not consent.diagnostics:
                continue
            if level in (PrivacyLevel.L1.value, PrivacyLevel.L2.value) and not consent.usage_metrics:
                continue
            validate_envelope_dict(event)
            current.append(event)
            if len(current) >= 50:
                batches.append(json.dumps(current))
                current = []
        if current:
            batches.append(json.dumps(current))
        return batches


class CollectorIngest:
    """Server-side re-validation + daily-peppered session hashing (unlinkability)."""

    def __init__(self, day_pepper: str) -> None:
        self.day_pepper = day_pepper
        self.alarm_count = 0

    def _hash_session(self, session_id: str | None) -> str | None:
        if session_id is None:
            return None
        digest = hashlib.sha256((session_id + self.day_pepper).encode()).hexdigest()
        return digest[:16]

    def ingest(self, batch_json: str) -> list[dict]:
        accepted: list[dict] = []
        for raw in json.loads(batch_json):
            try:
                env = validate_envelope_dict(raw)
            except TelemetryViolation:
                self.alarm_count += 1
                continue
            row = envelope_to_wire(env)
            row["session_id"] = self._hash_session(env.session_id)
            accepted.append(row)
        return accepted

    def suppress_small_cells(self, rows: list[dict]) -> list[dict]:
        counts: dict[tuple, set] = {}
        for row in rows:
            key = (row["timestamp"][:10], row["action"])
            counts.setdefault(key, set()).add(row["session_id"])
        return [
            row
            for row in rows
            if len(counts[(row["timestamp"][:10], row["action"])]) >= K_ANONYMITY_MIN_SESSIONS
        ]
