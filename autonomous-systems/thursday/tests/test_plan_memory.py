"""Tests for thursday/plan_memory.py's execution-feedback-loop additions:
schema migration, new-field round-trip, write-time redaction, and retention
still preserving the new columns. Uses THURSDAY_PLAN_MEMORY_DB/_ARCHIVE to
isolate each test in a fresh temp file -- never touches a real installation.
"""

from __future__ import annotations

import json
import os
import sqlite3

import pytest

from thursday import plan_memory as pm


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "plan_memory.sqlite3"
    archive_path = tmp_path / "plan_memory_archive.jsonl"
    monkeypatch.setenv("THURSDAY_PLAN_MEMORY_DB", str(db_path))
    monkeypatch.setenv("THURSDAY_PLAN_MEMORY_ARCHIVE", str(archive_path))
    yield db_path, archive_path


def test_init_db_migrates_existing_legacy_schema(_isolated_db):
    db_path, _ = _isolated_db
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE plan_memory (
            plan_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, query TEXT NOT NULL,
            abstract TEXT NOT NULL, steps TEXT NOT NULL, executed_steps TEXT NOT NULL,
            status TEXT NOT NULL, service_id TEXT, result_summary TEXT, lesson TEXT,
            tags TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO plan_memory VALUES ('old-1','2020-01-01','q','a','[]','[]','completed',NULL,NULL,NULL,'')"
    )
    conn.commit()
    conn.close()

    pm.init_db()

    cols = {row[1] for row in sqlite3.connect(str(db_path)).execute("PRAGMA table_info(plan_memory)").fetchall()}
    assert {"decision_type", "provider", "model", "confidence", "latency_s", "failure_reason", "raw_step_count"} <= cols

    row = pm.get_plan_trace("old-1")
    assert row is not None
    assert row["query"] == "q"
    assert row["raw_step_count"] == 0
    assert row["provider"] is None


def test_init_db_is_idempotent(_isolated_db):
    pm.init_db()
    pm.init_db()  # must not raise (duplicate ALTER TABLE / CREATE TABLE)


def test_save_plan_trace_round_trips_new_fields(_isolated_db):
    pid = pm.save_plan_trace(
        query="check business status", abstract="route to business_status", steps=[], status="success",
        service_id="business_status", decision_type="plan", provider="mlx_lm", model="qwen3.5-4b",
        confidence="high", latency_s=12.5, failure_reason=None, raw_step_count=1,
    )
    row = pm.get_plan_trace(pid)
    assert row["decision_type"] == "plan"
    assert row["provider"] == "mlx_lm"
    assert row["model"] == "qwen3.5-4b"
    assert row["confidence"] == "high"
    assert row["latency_s"] == 12.5
    assert row["raw_step_count"] == 1


def test_save_plan_trace_records_failure_reason(_isolated_db):
    pid = pm.save_plan_trace(
        query="do something risky", abstract="LLM call failed: timed out", steps=[], status="abstained",
        failure_reason="llm_call_failed",
    )
    row = pm.get_plan_trace(pid)
    assert row["failure_reason"] == "llm_call_failed"


def test_save_plan_trace_redacts_top_level_fields(_isolated_db):
    pid = pm.save_plan_trace(
        query="my password: hunter2", abstract="normal", steps=[], status="chat",
        result_summary="api key = sk-abcdefghij1234567890", lesson="password: hunter2",
    )
    row = pm.get_plan_trace(pid)
    assert "hunter2" not in row["query"]
    assert "[REDACTED]" in row["query"]
    assert "sk-abcdefghij1234567890" not in row["result_summary"]
    assert "hunter2" not in row["lesson"]


def test_save_plan_trace_redacts_nested_step_params(_isolated_db):
    pid = pm.save_plan_trace(
        query="hi", abstract="a", status="success",
        steps=[{"kind": "service", "service_id": "admin_agent", "params": {"body": "api key: sk-abcdefghij1234567890"}}],
    )
    row = pm.get_plan_trace(pid)
    assert row["steps"][0]["params"]["body"] == "api key: [REDACTED]"


def test_save_plan_trace_fail_soft_on_broken_connection(_isolated_db, monkeypatch):
    def _boom():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(pm, "_get_conn", _boom)
    result = pm.save_plan_trace(query="hi", abstract="a", steps=[], status="chat")
    assert result is None


def test_retention_archival_preserves_new_columns(_isolated_db, monkeypatch):
    db_path, archive_path = _isolated_db
    monkeypatch.setattr(pm, "ACTIVE_LIMIT", 3)
    for i in range(5):
        pm.save_plan_trace(
            query=f"request {i}", abstract="a", steps=[], status="success",
            provider="mlx_lm", model="qwen3.5-4b", raw_step_count=i,
        )
    assert archive_path.exists()
    archived = [json.loads(line) for line in archive_path.read_text().splitlines() if line.strip()]
    assert len(archived) == 2  # 5 inserted, cap 3 -> 2 evicted
    assert all("provider" in rec and rec["provider"] == "mlx_lm" for rec in archived)
