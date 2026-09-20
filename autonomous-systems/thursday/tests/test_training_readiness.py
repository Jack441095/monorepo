"""Tests for thursday/training_readiness.py (Phase 5 prep).

Seeds plans containing credentials/PII shapes in isolated stores and
proves the gate: redaction holds (0 leaks), counts are exact, and small
corpora correctly report NOT READY instead of green-lighting training.
"""

from __future__ import annotations

import pytest

from thursday import feedback as fb
from thursday import plan_memory as pm
from thursday import training_readiness as tr


@pytest.fixture(autouse=True)
def _isolated_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("THURSDAY_PLAN_MEMORY_DB", str(tmp_path / "plan_memory.sqlite3"))
    monkeypatch.setenv("THURSDAY_PLAN_MEMORY_ARCHIVE", str(tmp_path / "plan_memory_archive.jsonl"))
    monkeypatch.setattr(fb, "FEEDBACK_LOG", tmp_path / "feedback.jsonl")
    monkeypatch.setattr(fb, "HABITS_FILE", tmp_path / "habits.json")
    monkeypatch.setattr(fb, "PATTERNS_FILE", tmp_path / "patterns.json")
    monkeypatch.setattr(fb, "SUGGESTIONS_FILE", tmp_path / "suggestions.json")


def test_readiness_empty_stores_not_ready():
    report = tr.readiness_report()
    assert report["ok"] is True
    assert report["ready"] is False
    assert report["total"] == 0
    assert any("keep operating" in r for r in report["reasons"])


def test_readiness_counts_and_signals():
    pid = pm.save_plan_trace(query="quote mixing", abstract="route finance", steps=[],
                              status="chat", service_id="finance_admin", decision_type="plan")
    fb.record_feedback(turn_id="t1", plan_id=pid, explicit_rating=1)
    pm.save_plan_trace(query="hi", abstract="chat", steps=[], status="chat", decision_type="chat")
    report = tr.readiness_report()
    assert report["total"] == 2
    assert report["with_user_signal"] == 1
    assert report["by_decision_type"].get("plan") == 1
    assert report["ready"] is False  # below MIN_RECORDS


def test_readiness_leak_scan_catches_surviving_secrets(monkeypatch):
    import thursday.training_readiness as tr_mod
    planted = [{
        "plan_id": "leak-1",
        "decision": {"type": "plan", "abstract": "x", "steps": [], "confidence": "high"},
        "outcome": {"status": "success", "result_summary": "token THURSDAY_CONFIRMATION_SECRET=hunter2"},
        "user_signal": None,
    }]
    monkeypatch.setattr(tr_mod.te, "export_training_records", lambda limit=10000: planted)
    report = tr_mod.readiness_report()
    assert report["leak_plan_ids"] == ["leak-1"]
    assert report["ready"] is False
    assert any("FAIL CLOSED" in r for r in report["reasons"])


def test_readiness_seeded_credentials_do_not_leak():
    # Real pipeline check: credentials in the raw query must not survive
    # into the exported record (plan_memory redacts at save, export
    # redacts again) -- the gate must report 0 leaks.
    pm.save_plan_trace(query="contact Bearer abcdefgh12345678 about mix",
                       abstract="route", steps=[], status="chat", decision_type="chat")
    report = tr.readiness_report()
    assert report["leak_plan_ids"] == []
    assert "Bearer abcdefgh12345678" not in str(report)


def test_render_readiness_states_verdict():
    report = tr.readiness_report()
    out = tr.render_readiness(report)
    assert "FINETUNE READINESS" in out
    assert "NOT READY" in out
