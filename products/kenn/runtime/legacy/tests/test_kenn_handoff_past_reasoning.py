"""_strip_past_reasoning_block -- pure-function regression test.

Verified directly (2026-07-30, building the podcast-check explanations):
chat_answer.py's "Past reasoning on this topic" block is stitched in from a
GLOBAL, query-text-similarity lookup (kenn/knowledge/reasoning.py's
query_reasoning_traces), not scoped to session or topic. A set of
topically-different podcast checks asked back-to-back (hum, then rumble) had
the *rumble* answer's body replaced by the *hum* answer's conclusion, purely
because they shared enough vocabulary for the global lookup to match. This
block belongs in voice/TTS output (chat_answer.py says its own TTS layer
relies on the blank-line boundary to strip it before speech) but never in a
written report. No KENN index required -- pure string manipulation.
"""

from __future__ import annotations

from audio_analysis.integration.kenn_handoff import _strip_past_reasoning_block


def test_strips_the_block_between_its_blank_line_boundaries():
    answer = (
        "Here is the real answer.\n\n"
        "Past reasoning on this topic:\n"
        "- User query: \"unrelated question\"\n"
        "  Conclusion: some other conclusion entirely\n\n"
        "More of the real answer continues here."
    )
    cleaned = _strip_past_reasoning_block(answer)
    assert "Past reasoning" not in cleaned
    assert "unrelated question" not in cleaned
    assert "Here is the real answer." in cleaned
    assert "More of the real answer continues here." in cleaned


def test_leaves_answers_without_the_block_untouched():
    answer = "A perfectly normal answer with no past-reasoning block."
    assert _strip_past_reasoning_block(answer) == answer


def test_handles_the_block_at_the_very_end_of_the_answer():
    answer = "Real answer.\n\nPast reasoning on this topic:\nfoo\n\n"
    cleaned = _strip_past_reasoning_block(answer)
    assert "Past reasoning" not in cleaned
    assert "Real answer." in cleaned


def test_handles_empty_string():
    assert _strip_past_reasoning_block("") == ""
