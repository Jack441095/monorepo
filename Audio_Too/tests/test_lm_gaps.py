"""Tests for LM gap workflow (dedupe, resolve, retest)."""

from __future__ import annotations

import sys
from pathlib import Path

WEBSITE = Path(__file__).resolve().parent.parent / "server" / "app"
sys.path.insert(0, str(WEBSITE))

import lm_gaps  # noqa: E402
import tips_gaps  # noqa: E402


def test_normalize_question_collapses_whitespace() -> None:
    assert lm_gaps.normalize_question("  How   do I  sidechain?  ") == "how do i sidechain?"


def test_record_gap_dedupes_open() -> None:
    payload = {"confidence": "low", "sources": [], "topics": ["mix"]}
    first = lm_gaps.record_gap("Dedupe test question alpha", payload, channel="test")
    second = lm_gaps.record_gap("  dedupe   test question   alpha  ", payload, channel="test")
    assert first is not None
    assert second is not None
    assert second.get("deduped") is True
    assert second["id"] == first["id"]


def test_gap_is_resolved_requires_note_source() -> None:
    assert lm_gaps.gap_is_resolved({"confidence": "high", "sources": [{"kind": "note"}]}) is True
    assert lm_gaps.gap_is_resolved({"confidence": "high", "sources": [{"kind": "manual"}]}) is False
    assert lm_gaps.gap_is_resolved({"confidence": "low", "sources": [{"kind": "note"}]}) is False


def test_mark_resolved_and_dismiss_drafted() -> None:
    row = tips_gaps.record_gap(
        "resolve workflow test question",
        {"confidence": "low", "sources": [], "topics": []},
        channel="test",
    )
    assert row is not None
    tips_gaps.link_gap_note(row["id"], "test-gap-note.md")
    assert lm_gaps.dismiss_gap(row["id"]) is True
    gap = tips_gaps.get_gap(row["id"])
    assert gap is not None
    assert gap["status"] == "dismissed"


def test_retest_gap_marks_resolved(monkeypatch) -> None:
    row = tips_gaps.record_gap(
        "retest resolves when note hits",
        {"confidence": "low", "sources": [], "topics": []},
        channel="test",
    )
    assert row is not None

    def fake_retest(_question: str) -> dict:
        return {
            "confidence": "high",
            "sources": [{"kind": "note", "label": "Test Note"}],
            "answer": "Use compression on the vocal bus.",
        }

    monkeypatch.setattr(lm_gaps, "retest_question", fake_retest)
    result = lm_gaps.retest_gap(row["id"])
    assert result.get("resolved") is True
    gap = tips_gaps.get_gap(row["id"])
    assert gap is not None
    assert gap["status"] == "resolved"
