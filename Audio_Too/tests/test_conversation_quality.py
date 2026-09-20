"""Unit and integration tests for KENN conversation quality and context validation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.core.chat_routing import (
    normalize_history,
    clean_history_content,
    history_context_line,
    clarification_payload,
)
from kenn.core.chat_formatting import suggested_followups


def test_clean_history_content_removes_bullets_and_sources() -> None:
    assistant_text = (
        "Short answer: Turn the vocal down.\n"
        "Try this: Lower it.\n"
        "Sources:\n"
        "- vocal_notes.md\n"
        "You could also ask:\n"
        "- How to automate it?"
    )
    clean = clean_history_content(assistant_text, "assistant")
    assert "Sources:" not in clean
    assert "vocal_notes.md" not in clean
    assert "You could also ask:" not in clean
    assert "vocal" in clean


def test_normalize_history_limits_count_and_cleans() -> None:
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "Hi there!\nSources:\n- note"},
        {"role": "user", "content": "tell me about mixing"},
        {"role": "assistant", "content": "Mixing tips.\nSources:\n- note2"},
        {"role": "user", "content": "what next?"},
    ]
    clean = normalize_history(history)
    assert len(clean) <= 4
    # The cleaned assistant message should not contain 'Sources:'
    for turn in clean:
        if turn["role"] == "assistant":
            assert "Sources:" not in turn["content"]


def test_history_context_line_adds_metadata_labels() -> None:
    history = [{"role": "user", "content": "How do I fix muddy vocals?"}]
    context = history_context_line("what next?", history)
    assert context.startswith("[Previous User Question]:")
    assert "muddy vocals" in context


def test_repeated_clarification_provides_reset_guidance() -> None:
    # Set up history where assistant already asked to clarify
    history = [
        {"role": "user", "content": "something unclear"},
        {"role": "assistant", "content": "I can help, but I need one bit more direction first."},
    ]
    payload = clarification_payload("still unclear", history=history)
    assert payload["intent"] == "clarify"
    assert "trouble matching your question" in payload["answer"]
    assert "Let's reset" in payload["answer"]
    assert "typing 'reset'" in payload["answer"]


def test_suggested_followups_verifies_topic_grounding() -> None:
    # topic is 'mastering', but results only contain 'wwise' topic chunk
    topics = ["mastering", "wwise"]
    results = [
        (10.0, {"kind": "note", "topics": ["wwise"], "title": "Wwise Intro", "text": "Wwise details."})
    ]
    followups = suggested_followups(
        "wwise and mastering",
        related=[],
        topics=topics,
        history=None,
        results=results,
    )
    # The 'wwise' hints should be included since 'wwise' topic is in retrieved results.
    # The 'mastering' hints should NOT be included because 'mastering' topic is not in retrieved results.
    assert any("Wwise" in f for f in followups)
    assert not any("headroom before mastering" in f for f in followups)
    assert not any("LUFS" in f for f in followups)
