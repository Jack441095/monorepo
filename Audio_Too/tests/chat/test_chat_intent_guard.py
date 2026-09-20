"""Tests for strict intent matching in Audio Tips chat metadata."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.core.chat import confidence_level, intent_guard_status, results_are_weak, source_quality_level  # noqa: E402


def note(source: str, title: str, text: str) -> dict:
    return {
        "kind": "note",
        "source": source,
        "title": title,
        "text": text,
        "page": 0,
    }


def test_intent_guard_rejects_broad_topic_without_specific_match() -> None:
    query = "How do I make vocals sound wide without muddying the mix?"
    results = [
        (
            12.0,
            note(
                "vocal-deessing-and-sibilance.md",
                "Vocal De-Essing And Sibilance",
                "Tags: vocals, eq, harsh, deesser\nTreat harsh S and T sounds before adding brightness.",
            ),
        )
    ]

    assert intent_guard_status(query, results) == "weak"
    assert confidence_level(query, results) == "low"
    assert source_quality_level(query, results) == "low"


def test_intent_guard_accepts_note_with_specific_match() -> None:
    query = "How do I make vocals sound wide without muddying the mix?"
    results = [
        (
            12.0,
            note(
                "vocal-width-without-mud.md",
                "Vocal Width Without Mud",
                "Tags: vocals, stereo width, width, wide, mono\nKeep the lead vocal central and widen doubles.",
            ),
        )
    ]

    assert intent_guard_status(query, results) == "strong"
    assert confidence_level(query, results) == "high"
    assert source_quality_level(query, results) == "high"


def test_topicless_query_rejects_note_without_title_or_tag_match() -> None:
    query = "sorry wrong LLM thought you were DeepSeek"
    results = [
        (
            20.0,
            note(
                "deliver-final-mix-to-client.md",
                "Deliver Final Mix To Client",
                "Tags: delivery, export\nDo not send the wrong final mix file to a client.",
            ),
        )
    ]

    assert results_are_weak(query, results) is True
    assert confidence_level(query, results) == "low"
