"""Tests for thursday/training_export.py -- the read-only join of
plan_memory + feedback.jsonl into training-ready records. No LLM calls;
exercises the join/redaction/atomic-write logic directly against isolated
temp stores.
"""

from __future__ import annotations

import json

import pytest

from thursday import feedback as fb
from thursday import plan_memory as pm
from thursday import training_export as te


@pytest.fixture(autouse=True)
def _isolated_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("THURSDAY_PLAN_MEMORY_DB", str(tmp_path / "plan_memory.sqlite3"))
    monkeypatch.setenv("THURSDAY_PLAN_MEMORY_ARCHIVE", str(tmp_path / "plan_memory_archive.jsonl"))
    monkeypatch.setattr(fb, "FEEDBACK_LOG", tmp_path / "feedback.jsonl")
    monkeypatch.setattr(fb, "HABITS_FILE", tmp_path / "habits.json")
    monkeypatch.setattr(fb, "PATTERNS_FILE", tmp_path / "patterns.json")
    monkeypatch.setattr(fb, "SUGGESTIONS_FILE", tmp_path / "suggestions.json")
    yield tmp_path


def test_export_empty_stores_returns_empty_list():
    assert te.export_training_records() == []


def test_export_joins_plan_and_feedback_by_plan_id():
    pid = pm.save_plan_trace(query="check client", abstract="route", steps=[], status="success",
                              service_id="client_info", decision_type="plan", provider="mlx_lm",
                              model="qwen3.5-4b", confidence="high", latency_s=3.2)
    fb.record_feedback(turn_id="t1", plan_id=pid, explicit_rating=1, correction_from="client_info",
                        correction_to="business_status")

    records = te.export_training_records()
    assert len(records) == 1
    rec = records[0]
    assert rec["plan_id"] == pid
    assert rec["model_meta"] == {"provider": "mlx_lm", "model": "qwen3.5-4b", "latency_s": 3.2}
    assert rec["user_signal"]["explicit_rating"] == 1
    assert rec["user_signal"]["correction_to"] == "business_status"


def test_export_handles_plan_with_no_matching_feedback():
    pm.save_plan_trace(query="hi", abstract="chat", steps=[], status="chat", decision_type="chat")
    records = te.export_training_records()
    assert len(records) == 1
    assert records[0]["user_signal"] is None


def test_export_redacts_recursively_in_steps_params():
    pm.save_plan_trace(
        query="hi", abstract="a", status="success",
        steps=[{"kind": "service", "service_id": "admin_agent",
                "params": {"body": "api key: sk-abcdefghij1234567890"}}],
    )
    records = te.export_training_records()
    # already redacted at write time by plan_memory.save_plan_trace, and
    # training_export's own redact() pass is a no-op on already-clean text
    assert "sk-abcdefghij1234567890" not in json.dumps(records[0]["decision"]["steps"])


def test_export_since_filters_by_created_at():
    pm.save_plan_trace(query="old one", abstract="a", steps=[], status="chat", plan_id="old-plan")
    # created_at is set internally to "now" -- force a clearly-future cutoff
    # to prove the filter actually excludes rows, not just passes everything.
    records = te.export_training_records(since="2999-01-01T00:00:00+00:00")
    assert records == []


def test_write_training_jsonl_atomic_and_countable(tmp_path):
    pm.save_plan_trace(query="a", abstract="a", steps=[], status="chat")
    pm.save_plan_trace(query="b", abstract="b", steps=[], status="chat")
    out_path = tmp_path / "export.jsonl"
    count = te.write_training_jsonl(out_path)
    assert count == 2
    lines = out_path.read_text().splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)  # must be valid JSON


def test_export_fails_soft_on_broken_plan_memory(monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError("db exploded")

    import thursday.plan_memory as pm_module
    monkeypatch.setattr(pm_module, "list_plan_history", _boom)
    assert te.export_training_records() == []
