"""Tests for question suggestions and LLM follow-up parsing."""

from __future__ import annotations

import sys
from pathlib import Path

LM = Path(__file__).resolve().parent.parent / "studio" / "kenn" / "kenn"
sys.path.insert(0, str(LM.parent))

from kenn.core.suggestions import (  # noqa: E402
    merge_followups,
    parse_followups_from_answer,
    starter_questions,
    typeahead,
)


def test_typeahead_matches_substring() -> None:
    out = typeahead("sidechain bass", limit=5)
    assert out
    assert any("sidechain" in item.lower() for item in out)


def test_starter_questions_returns_nonempty_list() -> None:
    out = starter_questions(limit=8)
    assert len(out) >= 3
    assert all(isinstance(item, str) and item.endswith("?") for item in out)


def test_parse_followups_from_llm_answer() -> None:
    text = """Short answer:
Use compression.

You could also ask:
- How do I set release time on a compressor?
- What ratio works on vocals?
"""
    out = parse_followups_from_answer(text)
    assert len(out) >= 2
    assert "compressor" in out[0].lower()


def test_merge_followups_prefers_primary() -> None:
    merged = merge_followups(["First question?"], ["Second question?"], limit=2)
    assert merged[0] == "First question?"
