"""Tests for thursday/feedback.py's execution-feedback-loop additions:
the plan_id join key and the write-time redaction fix (previously response_
text/user_text were stored raw, with zero redaction applied anywhere in
this module).
"""

from __future__ import annotations

import json

import pytest

from thursday import feedback as fb


@pytest.fixture(autouse=True)
def _isolated_log(tmp_path, monkeypatch):
    log_path = tmp_path / "feedback.jsonl"
    monkeypatch.setattr(fb, "FEEDBACK_LOG", log_path)
    monkeypatch.setattr(fb, "HABITS_FILE", tmp_path / "habits.json")
    monkeypatch.setattr(fb, "PATTERNS_FILE", tmp_path / "patterns.json")
    monkeypatch.setattr(fb, "SUGGESTIONS_FILE", tmp_path / "suggestions.json")
    yield log_path


def test_record_feedback_stores_plan_id(_isolated_log):
    record = fb.record_feedback(turn_id="t1", service_id="client_info", plan_id="plan-abc")
    assert record["plan_id"] == "plan-abc"
    on_disk = json.loads(_isolated_log.read_text().splitlines()[0])
    assert on_disk["plan_id"] == "plan-abc"


def test_record_feedback_plan_id_defaults_to_none(_isolated_log):
    record = fb.record_feedback(turn_id="t1")
    assert record["plan_id"] is None


def test_record_feedback_redacts_response_and_user_text(_isolated_log):
    record = fb.record_feedback(
        turn_id="t1",
        response_text="here is your api key = sk-abcdefghij1234567890",
        user_text="my password: hunter2",
    )
    assert "sk-abcdefghij1234567890" not in record["response_text_snippet"]
    assert "[REDACTED]" in record["response_text_snippet"]
    assert "hunter2" not in record["user_text_snippet"]
    assert "[REDACTED]" in record["user_text_snippet"]


def test_record_feedback_snippet_still_truncated_to_200_chars(_isolated_log):
    long_text = "a" * 500
    record = fb.record_feedback(turn_id="t1", response_text=long_text, user_text=long_text)
    assert len(record["response_text_snippet"]) <= 200
    assert len(record["user_text_snippet"]) <= 200
