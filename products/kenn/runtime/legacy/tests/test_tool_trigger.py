"""Tests for explicit-only tool-trigger detection (Phase 3 of
docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md)."""

from __future__ import annotations

import pytest

from kenn.core.tool_trigger import detect_tool_trigger


@pytest.mark.parametrize(
    "text,expected",
    [
        ("run a mix review on this", "run_mix_review"),
        ("please run a mix review", "run_mix_review"),
        ("start the mix review", "run_mix_review"),
        ("review this mix", "run_mix_review"),
        ("review my track", "run_mix_review"),
        ("separate this into stems", "run_stem_separation"),
        ("please separate it into stems", "run_stem_separation"),
        ("split this into stems", "run_stem_separation"),
        ("run stem separation", "run_stem_separation"),
        ("start an automix", "run_automix"),
        ("run the automix", "run_automix"),
        ("render an automix pass", "run_automix"),
    ],
)
def test_explicit_imperative_phrasing_matches(text: str, expected: str) -> None:
    assert detect_tool_trigger(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "how do I run a mix review myself?",
        "what does stem separation actually do?",
        "can you explain how automix works?",
        "why would I separate stems before mixing?",
        "is a mix review worth it for a rough demo?",
        "this mix feels muddy, can you check it",
        "my mix sounds off, any ideas?",
        "how do I saturate sub bass without clipping?",
        "",
        "   ",
    ],
)
def test_indirect_or_question_phrasing_does_not_trigger(text: str) -> None:
    assert detect_tool_trigger(text) is None
