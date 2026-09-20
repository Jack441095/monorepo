"""Tests for note-vs-manual ranking in chat answers."""

from __future__ import annotations

import sys
from pathlib import Path

ABLETON = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn"
sys.path.insert(0, str(ABLETON.parent))

from kenn.core.chat import answer_payload, chunk_is_catalog_boilerplate, prefer_note_over_manual  # noqa: E402


def test_catalog_boilerplate_detected() -> None:
    chunk = {
        "kind": "manual",
        "text": "Category: ableton\nTitle: Live Manual\nTopics: midi\n\nSome body text.",
    }
    assert chunk_is_catalog_boilerplate(chunk) is True


def test_prefer_note_when_topics_match() -> None:
    note = (
        6.0,
        {
            "kind": "note",
            "title": "Vocal Compression",
            "source": "vocal-compression-chain.md",
            "text": "Tags: vocal, compression\nShort answer: Use gentle compression.",
        },
    )
    manual = (
        8.0,
        {
            "kind": "manual",
            "text": "Category: ableton\nTitle: Manual\nTopics: general\nBody",
        },
    )
    assert prefer_note_over_manual(note, manual, ["vocals", "compression"]) is True


def test_sidechain_pump_wording_prefers_specific_workflow_note() -> None:
    payload = answer_payload(
        "My sidechain pumps too much; how should I set attack and release?",
        limit=4,
        allow_llm=False,
    )

    assert payload["weak_match"] is False
    assert payload["sources"][0]["source"] == "sidechain-bass-to-kick.md"
    assert "release" in payload["answer"].lower()
