"""Tests for KENN query logging and answer-quality issue detection."""

from __future__ import annotations

import sys
from pathlib import Path

WEBSITE = Path(__file__).resolve().parent.parent / "server" / "app"
sys.path.insert(0, str(WEBSITE))

import db  # noqa: E402
import lm_gaps  # noqa: E402
import llm_improvement  # noqa: E402
import tips_queries  # noqa: E402


def test_record_query_stores_answer_self_check(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    payload = {
        "confidence": "high",
        "source_quality": "high",
        "route": "production",
        "intent": "steps",
        "topics": ["vocals"],
        "sources": [{"label": "Wrong Source", "kind": "note"}],
        "answer_self_check": {
            "passed": False,
            "warnings": ["answer may miss exact query terms"],
        },
        "grounding": {"score": 58, "warnings": ["answer may miss intent"]},
        "grounding_mode": "medium",
    }

    row = tips_queries.record_query("How do I make vocals wide?", payload, channel="test")
    items = tips_queries.list_quality_issues()

    assert row["route"] == "production"
    assert len(items) == 1
    assert items[0]["id"] == row["id"]
    assert items[0]["grounding_score"] == 58
    assert items[0]["grounding_mode"] == "medium"
    assert items[0]["self_check_warnings"] == ["answer may miss exact query terms"]


def test_self_check_warning_records_gap(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    payload = {
        "confidence": "high",
        "sources": [{"label": "A Note", "kind": "note"}],
        "answer_self_check": {
            "passed": False,
            "warnings": ["source topics do not match query topics"],
        },
    }

    gap = lm_gaps.record_gap("How do I make vocals wide?", payload, channel="test")

    assert gap is not None
    assert gap["deduped"] is False


def test_draft_eval_from_logged_query(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(llm_improvement, "DRAFT_EVAL_PATH", tmp_path / "draft_feedback_cases.json")
    row = tips_queries.record_query(
        "How do I make vocals wide?",
        {
            "confidence": "high",
            "source_quality": "high",
            "route": "production",
            "intent": "steps",
            "topics": ["vocals", "stereo_width"],
            "sources": [{"label": "Vocal De-Essing", "kind": "note"}],
            "answer_self_check": {
                "passed": False,
                "warnings": ["answer may miss exact query terms"],
            },
        },
        channel="test",
    )

    result = llm_improvement.draft_eval_from_query(row["id"])

    assert result["ok"] is True
    assert result["case"]["question"] == "How do I make vocals wide?"
    assert "stereo_width" in result["case"]["topics_must_include"]
