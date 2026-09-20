"""Tests for input-aware chat follow-up suggestions."""

from __future__ import annotations

import sys
from pathlib import Path

LM = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn"
sys.path.insert(0, str(LM.parent))

from kenn.core.chat import related_from_results, suggested_followups  # noqa: E402
from kenn.core.suggestions import parse_followups_from_answer  # noqa: E402


def test_suggested_followups_uses_note_related_section() -> None:
    related = ["How do I sidechain bass to the kick?"]
    out = suggested_followups(
        "How do I saturate sub bass?",
        related,
        ["bass", "saturation"],
        results=None,
    )
    assert related[0] in out


def test_suggested_followups_adds_intent_hint_for_how_questions() -> None:
    out = suggested_followups("How do I set up a delay in Ableton?", [], ["delay"], results=None)
    assert any("device" in item.lower() or "step" in item.lower() for item in out)


def test_related_from_results_reads_approved_note() -> None:
    note_path = LM / "Training_Data_Notes" / "sidechain-bass-to-kick.md"
    assert note_path.exists()
    text = note_path.read_text(encoding="utf-8")
    chunk = {
        "kind": "note",
        "source": "sidechain-bass-to-kick.md",
        "title": "Sidechain Bass To Kick",
        "text": text[:800],
    }
    out = related_from_results("How do I sidechain bass?", [(12.0, chunk)])
    assert any("sidechain" in item.lower() for item in out)


def test_parse_followups_from_llm_section() -> None:
    answer = """You could also ask:
- How do I automate filter cutoff?
"""
    parsed = parse_followups_from_answer(answer)
    assert any("automate" in q.lower() for q in parsed)
