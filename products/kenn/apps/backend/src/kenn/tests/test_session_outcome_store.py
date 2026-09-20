from __future__ import annotations

from kenn.core.session_outcome_contract import SCHEMA, STAGES
from kenn.core.session_outcome_store import SessionOutcomeStore


def _bucket(value: int) -> str:
    return "sha256:" + f"{value:064x}"


def _outcome() -> dict:
    return {
        "schema": SCHEMA, "session_bucket": _bucket(1), "project_bucket": _bucket(2),
        "tester_bucket": _bucket(3), "intent_class": "advice", "context_freshness": "fresh",
        "evidence_classes": ["live_snapshot", "official_ableton_manual"],
        "lifecycle_outcome": "completed", "user_verdict": "keep", "reason_codes": [],
        "root_cause": None, "latency_ms": {stage: 1 for stage in STAGES},
        "contains_raw_prompt": False, "contains_audio": False,
    }


def test_store_persists_only_valid_category_level_outcome(tmp_path) -> None:
    store = SessionOutcomeStore(tmp_path / "outcomes.sqlite3")
    result = store.record(_outcome())

    assert result["ok"] is True
    assert result["live_mutation_authorized"] is False
    saved = store.recent()
    assert saved[0]["schema"] == SCHEMA
    assert "please make it louder" not in str(saved[0]).lower()


def test_store_rejects_raw_content_before_persistence(tmp_path) -> None:
    store = SessionOutcomeStore(tmp_path / "outcomes.sqlite3")
    unsafe = _outcome()
    unsafe["prompt"] = "please make it louder"

    result = store.record(unsafe)

    assert result == {"ok": False, "schema": SCHEMA, "errors": ["raw_content", "schema_fields"], "stored": False}
    assert store.recent() == []


def test_store_summary_returns_only_bounded_aggregate_feedback(tmp_path) -> None:
    store = SessionOutcomeStore(tmp_path / "outcomes.sqlite3")
    keep = _outcome()
    revise = _outcome()
    revise.update({
        "intent_class": "apply",
        "lifecycle_outcome": "failed",
        "user_verdict": "revise",
        "root_cause": "readback_recovery",
        "latency_ms": {stage: 2 for stage in STAGES},
    })
    assert store.record(keep)["ok"] is True
    assert store.record(revise)["ok"] is True

    summary = store.summary(limit=10)

    assert summary["schema"] == "kenn.session_outcome_summary.v1"
    assert summary["sample_count"] == 2
    assert summary["valid_sample_count"] == 2
    assert summary["counts"]["intent_class"] == {"advice": 1, "apply": 1}
    assert summary["counts"]["root_cause"] == {"readback_recovery": 1}
    assert summary["reviewable_miss_count"] == 1
    assert summary["root_cause_label_rate"] == 1.0
    assert summary["mean_latency_ms"]["apply"] == 1.5
    assert summary["privacy"]["records_returned"] is False
    assert "sha256:" not in str(summary)
