"""Bounded local persistence for privacy-safe supervised-session outcomes."""

from __future__ import annotations

from datetime import datetime, timezone
from collections import Counter
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from kenn.core.session_memory import DB_PATH
from kenn.core.session_outcome_contract import ALLOWED_KEYS, SCHEMA, validate
from kenn.core.session_outcome_contract import STAGES


MAX_OUTCOMES = 500
SUMMARY_SCHEMA = "kenn.session_outcome_summary.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS supervised_session_outcomes (
            outcome_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS supervised_session_outcomes_created ON supervised_session_outcomes(created_at DESC)")
    return conn


class SessionOutcomeStore:
    """Persist only validator-approved, category-level evaluation records."""

    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)

    def record(self, outcome: dict[str, Any]) -> dict[str, Any]:
        failures = validate(outcome)
        if isinstance(outcome, dict) and set(outcome) != ALLOWED_KEYS:
            failures = sorted(set(failures + ["schema_fields"]))
        if failures:
            return {"ok": False, "schema": SCHEMA, "errors": failures, "stored": False}
        record = {key: outcome[key] for key in sorted(outcome)}
        record["outcome_id"] = f"outcome-{uuid4().hex}"
        record["recorded_at"] = _now()
        conn = _connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO supervised_session_outcomes(outcome_id, payload_json, created_at) VALUES (?, ?, ?)",
                (record["outcome_id"], json.dumps(record, separators=(",", ":"), sort_keys=True), record["recorded_at"]),
            )
            conn.execute(
                "DELETE FROM supervised_session_outcomes WHERE outcome_id IN ("
                "SELECT outcome_id FROM supervised_session_outcomes ORDER BY created_at DESC LIMIT -1 OFFSET ?)",
                (MAX_OUTCOMES,),
            )
            conn.commit()
        finally:
            conn.close()
        return {
            "ok": True, "schema": SCHEMA, "outcome_id": record["outcome_id"],
            "recorded_at": record["recorded_at"], "stored": True,
            "advisory_only": True, "live_mutation_authorized": False,
        }

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 100))
        conn = _connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT payload_json FROM supervised_session_outcomes ORDER BY created_at DESC LIMIT ?", (bounded,),
            ).fetchall()
        finally:
            conn.close()
        return [json.loads(row["payload_json"]) for row in rows]

    def summary(self, limit: int = 100) -> dict[str, Any]:
        """Return aggregate feedback signals without exposing stored records."""
        rows = self.recent(limit)
        valid = [row for row in rows if isinstance(row, dict) and not validate(row)]
        intents: Counter[str] = Counter()
        outcomes: Counter[str] = Counter()
        verdicts: Counter[str] = Counter()
        root_causes: Counter[str] = Counter()
        evidence_classes: Counter[str] = Counter()
        latency_totals: Counter[str] = Counter()
        reviewable_misses = 0
        labelled_misses = 0
        for row in valid:
            intents[str(row["intent_class"])] += 1
            outcomes[str(row["lifecycle_outcome"])] += 1
            verdicts[str(row["user_verdict"])] += 1
            evidence_classes.update(str(item) for item in row["evidence_classes"])
            if row["user_verdict"] in {"revise", "reject", "unsafe"}:
                reviewable_misses += 1
                if row.get("root_cause"):
                    labelled_misses += 1
            if row.get("root_cause"):
                root_causes[str(row["root_cause"])] += 1
            for stage in STAGES:
                latency_totals[stage] += int(row["latency_ms"][stage])
        count = len(valid)
        return {
            "schema": SUMMARY_SCHEMA,
            "sample_count": len(rows),
            "valid_sample_count": count,
            "invalid_sample_count": len(rows) - count,
            "counts": {
                "intent_class": dict(sorted(intents.items())),
                "lifecycle_outcome": dict(sorted(outcomes.items())),
                "user_verdict": dict(sorted(verdicts.items())),
                "root_cause": dict(sorted(root_causes.items())),
                "evidence_class": dict(sorted(evidence_classes.items())),
            },
            "reviewable_miss_count": reviewable_misses,
            "root_cause_labeled_miss_count": labelled_misses,
            "root_cause_label_rate": labelled_misses / reviewable_misses if reviewable_misses else 1.0,
            "mean_latency_ms": {
                stage: round(latency_totals[stage] / count, 3) if count else 0.0
                for stage in STAGES
            },
            "privacy": {
                "records_returned": False,
                "opaque_buckets_returned": False,
                "raw_prompts_returned": False,
                "audio_returned": False,
                "paths_returned": False,
                "identities_returned": False,
            },
            "limitations": [
                "Aggregate supervised-session feedback only; it does not replace human musical evaluation or beta qualification.",
                "The summary is bounded to the requested recent sample and does not expose individual session records.",
            ],
            "advisory_only": True,
            "live_mutation_authorized": False,
        }


__all__ = ["MAX_OUTCOMES", "SUMMARY_SCHEMA", "SessionOutcomeStore"]
