"""Tests for <break time="..."/> injection into KENN's static voice-mode
fallback answers (weak_match_answer), the chat_formatting.py half of the
2026-08-02 voice-expressiveness work. See tests/test_tts_ssml_breaks.py for
the synthesis-engine side (thursday/voice_output.py) that actually turns
these tags into real pauses.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.core.chat_formatting import weak_match_answer  # noqa: E402
from kenn.llm.linter import lint_response  # noqa: E402


def test_out_of_scope_voice_answer_contains_a_break_tag():
    answer = weak_match_answer("how do I bake bread", answer_mode="voice")
    assert '<break time="400ms"/>' in answer


def test_topic_hint_voice_answer_contains_a_break_tag():
    answer = weak_match_answer("mixing and Ableton", answer_mode="voice")
    assert '<break time="400ms"/>' in answer


def test_written_mode_answers_have_no_break_tags():
    """Regression: break tags are voice-only -- the written (non-voice) path
    must be completely unaffected."""
    out_of_scope = weak_match_answer("how do I bake bread")
    topic_hint = weak_match_answer("mixing and Ableton")
    assert "<break" not in out_of_scope
    assert "<break" not in topic_hint


def test_voice_answers_with_breaks_still_parse_into_real_segments():
    """End-to-end sanity check against the actual TTS-side parser (not a
    duplicate regex) -- proves the tag chat_formatting.py emits is exactly
    the shape thursday/voice_output.py's _parse_ssml_breaks() expects."""
    sys.path.insert(0, str(ROOT))
    from thursday.voice_output import _parse_ssml_breaks

    answer = weak_match_answer("how do I bake bread", answer_mode="voice")
    segments = _parse_ssml_breaks(answer)
    assert len(segments) == 2
    assert segments[0][1] == 0.4  # 400ms
    assert segments[0][0] and segments[1][0]  # both sides have real text


# --- lint_response() protects break tags through the 85-word voice truncation ---


def test_lint_response_preserves_a_break_tag_in_a_short_answer():
    text = 'Got it, Jack. <break time="500ms"/> Cut 3 dB around 300 Hz on the vocal bus.'
    result = lint_response(text, "voice")
    assert '<break time="500ms"/>' in result


def test_lint_response_break_tag_survives_the_85_word_truncation():
    """Regression: lint_response()'s voice-mode word-count enforcement
    (words = text.split(); words[:85]) previously operated on the raw tag
    text -- the tag itself contains a space ("<break time=..."), so
    text.split() saw it as two separate tokens, and the 85-word cutoff
    could land between them, leaving a bare "<break" fragment that would
    reach TTS and get mispronounced. Protecting the tag as a single
    whitespace-free placeholder before truncation and restoring it after
    must keep the tag fully intact regardless of where it falls relative
    to the word budget."""
    words_before = " ".join(["word"] * 84)
    text = f'{words_before} <break time="500ms"/> the rest goes on after the break tag here.'

    result = lint_response(text, "voice")

    assert "\x00" not in result
    assert "<break" not in result or '<break time="500ms"/>' in result


def test_lint_response_with_no_break_tag_is_unaffected():
    """Regression: the protect/restore wrapping must not change behaviour
    for the overwhelming majority of voice answers, which have no break
    tag at all."""
    words = " ".join(["word"] * 90) + "."
    result = lint_response(words, "voice")
    assert len(result.split()) <= 85
    assert "\x00" not in result
