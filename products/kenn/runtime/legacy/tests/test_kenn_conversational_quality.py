"""Unit and integration tests for KENN conversational quality, tone, and formatting constraints.

These tests ensure KENN communicates naturally like a small language model (warm, witty, concise, professional tone, proper contractions)
and adheres to channel-specific formatting constraints (written vs voice).
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.core.chat_routing import (
    conversational_intent,
    conversational_payload,
    should_use_history,
    clarification_payload,
    impossible_promise_payload,
)
from kenn.core.chat_answer import answer_payload
from kenn.core.chat_formatting import weak_match_answer
from kenn.llm.llm_rewrite import (
    generate_conversational_llm_response,
    is_enabled,
    LLMUsage,
    valid_response,
    CONVERSATIONAL_SYSTEM_PROMPT,
)
from kenn.llm.linter import lint_response


def test_conversational_intent_classification() -> None:
    """Verify that casual conversational phrases are correctly classified."""
    # Test greetings
    for q in ["hello", "hi there", "yo, how is it going?", "good morning"]:
        assert conversational_intent(q) in ("greeting", "check_in"), f"Failed on greeting: {q}"

    # Test thanks
    for q in ["thanks", "thank you so much", "cheers!"]:
        assert conversational_intent(q) == "thanks", f"Failed on thanks: {q}"

    # Test joke
    for q in ["tell me a joke", "something funny", "give me some banter"]:
        assert conversational_intent(q) == "joke", f"Failed on joke: {q}"

    # Test meta
    for q in ["who are you", "what are you", "wrong bot"]:
        assert conversational_intent(q) == "meta", f"Failed on meta: {q}"

    # Test non-conversational (technical)
    for q in ["how do I process kicks", "eq dynamic settings", "wwise mobile playback"]:
        assert conversational_intent(q) == "", f"Failed on technical query: {q}"


def test_conversational_payload_without_llm() -> None:
    """Verify canned responses are used when LLM is not enabled."""
    with patch("kenn.llm.llm_rewrite.is_enabled", return_value=False):
        payload = conversational_payload("hello")
        assert payload is not None
        assert payload["conversation_only"] is True
        assert payload["confidence"] == "high"
        assert payload["sources"] == []
        assert len(payload["answer"]) > 0

        # Check that it uses one of our warm greeting/check-in phrases
        assert any(
            phrase in payload["answer"]
            for phrase in ["Hey!", "Yo!", "Hey there!", "Good day!", "dive into some audio", "stems"]
        )


def test_conversational_payload_with_llm(monkeypatch) -> None:
    """Verify LLM responses are used when LLM is enabled."""
    monkeypatch.setenv("AUDIO_TOO_LLM_ENABLED", "1")
    monkeypatch.setenv("AUDIO_TOO_LLM_API_KEY", "test-api-key")

    mock_response = "Hey Jack! I'm ready to mix some tracks with you."
    mock_usage = LLMUsage(model="mock-model", provider="mock-provider", total_tokens=10)

    with (
        patch("kenn.llm.llm_rewrite._chat_completion", return_value=(mock_response, mock_usage)),
        patch("kenn.llm.llm_rewrite.is_enabled", return_value=True),
    ):
        payload = conversational_payload("yo KENN")
        assert payload is not None
        assert payload["answer"] == mock_response
        assert payload["llm_enhanced"] is True
        assert payload["conversation_only"] is True


def test_generate_conversational_llm_response_basic(monkeypatch) -> None:
    """Verify basic wrapper logic of generate_conversational_llm_response."""
    # 1. Disabled path
    # Keep the disabled branch independent of a developer .env that enables
    # the optional local LLM for interactive use.
    monkeypatch.setenv("AUDIO_TOO_LLM_ENABLED", "0")
    assert generate_conversational_llm_response("hello") is None

    # 2. Enabled path
    monkeypatch.setenv("AUDIO_TOO_LLM_ENABLED", "1")
    mock_response = "Alright mate, let's look at the routing."
    mock_usage = LLMUsage(model="mock-model", provider="mock-provider", total_tokens=20)

    with patch("kenn.llm.llm_rewrite._chat_completion", return_value=(mock_response, mock_usage)):
        res = generate_conversational_llm_response("yo", history=[{"role": "user", "content": "hi"}])
        assert res == mock_response


def test_voice_channel_formatting_constraints() -> None:
    """Verify that voice channel formatting correctly strips markdown elements and remains concise."""
    # Voice mode is meant for text-to-speech. Must not have markdown symbols, and must be under 80-85 words.
    voice_input = (
        "Short answer: Cut the mud.\n"
        "Try this:\n"
        "1. Put EQ on track.\n"
        "2. Set filter to 100 Hz.\n"
        "See [Note](file:///notes/eq.md) for more details.\n"
        "| Parameter | Value |\n"
        "|---|---|\n"
        "| Freq | 100 Hz |"
    )

    # 1. Linting behavior: Should strip tables, markdown links, bullet/list symbols, collapsing whitespace
    cleaned = lint_response(voice_input, "voice")
    assert "|" not in cleaned
    assert "---" not in cleaned
    assert "file://" not in cleaned
    assert "[" not in cleaned
    assert "]" not in cleaned
    assert "Note" in cleaned

    # 2. Validation behavior:
    # A correct voice response should be simple, natural spoken English without headings or list characters
    valid_voice = "You've got some mud in the low end of the vocals. Try inserting an EQ and cutting around 100 Hz."
    assert valid_response(valid_voice, "voice") is True

    # Reject if it contains headings
    assert valid_response("Short answer: Cut mud.", "voice") is False

    # Reject if too long
    excessive_voice = "word " * 120
    assert valid_response(excessive_voice, "voice") is False


def test_written_channel_formatting_constraints() -> None:
    """Verify written responses require proper structure like headers and sources."""
    # Quick fix format requires headings
    valid_written = "Short answer: Yes.\nTry this: Do it.\nSources:\n- Note"
    assert valid_response(valid_written, "quick_fix") is True

    # Rejects unstructured text
    assert valid_response("Just cut the mud.", "quick_fix") is False


def test_out_of_scope_abstention_behavior() -> None:
    """Verify out-of-scope questions get weak_match and list of capabilities instead of fabricated responses."""
    # Using a longer query containing out of scope words to prevent classification as unclear/clarify
    off_topic = "what is the best accounting software to invest all of my hard earned studio revenue in next year"
    payload = answer_payload(off_topic, limit=5, allow_llm=False)

    # Must abstain gracefully
    assert payload.get("confidence") == "low"
    assert payload.get("weak_match") is True
    assert payload.get("sources") == []

    # The answer should direct the user to what KENN actually specializes in
    answer = payload.get("answer", "")
    assert "audio engineering" in answer.lower()
    assert "mixing" in answer.lower()
    assert "ableton" in answer.lower()
    assert "accounting" not in answer.lower()


def test_tone_and_contractions() -> None:
    """Verify KENN's system prompt and canned responses enforce natural, warm tone and contractions."""
    # The system prompt must enforce contractions and UK spelling
    assert "UK spelling" in CONVERSATIONAL_SYSTEM_PROMPT
    assert "contractions" in CONVERSATIONAL_SYSTEM_PROMPT
    assert "warm, witty" in CONVERSATIONAL_SYSTEM_PROMPT

    # Canned responses should use natural contractions
    greeting_payload = conversational_payload("hello")
    # Verify the fallback answer has some friendly tone or contractions
    ans = greeting_payload["answer"]
    assert any(c in ans for c in ["'", "!", "thanks", "Ready", "good", "Great"])


def test_history_and_pronouns_routing() -> None:
    """Verify multi-turn history tracking correctly carries context for pronouns but ignores it for topic changes."""
    history = [
        {"role": "user", "content": "How do I fix muddy vocals?"},
        {"role": "assistant", "content": "Short answer: Use a high pass filter."},
    ]

    # Follow-up using pronoun "it" should use history
    assert should_use_history("how do I automate it?", history) is True
    assert should_use_history("explain that more", history) is True

    # Shifting topic completely should not carry over history
    assert should_use_history("how do I build SoundBanks in Wwise?", history) is False


def test_linter_error_redaction() -> None:
    """Verify that response linter strips out internal error and database logs."""
    raw_error = "The database query failed: Database error: lost connection. Traceback (most recent call last): line 10. Here is the actual answer."
    cleaned = lint_response(raw_error, "quick_fix")

    assert "database error" not in cleaned.lower()
    assert "traceback" not in cleaned.lower()
    assert cleaned.strip().endswith("Here is the actual answer.")


def test_voice_optimized_fallbacks() -> None:
    """Verify that fallbacks/refusals/clarifications return clean voice scripts when in voice mode."""
    # 1. Out of scope / weak match in voice mode
    ans_out_of_scope = weak_match_answer("how do I bake bread", answer_mode="voice")
    assert "•" not in ans_out_of_scope
    assert "Here are a few things" not in ans_out_of_scope
    assert "mixing" in ans_out_of_scope

    # 2. Topic hint in voice mode
    ans_topics = weak_match_answer("mixing and Ableton", answer_mode="voice")
    assert "1." not in ans_topics
    assert "For example:" not in ans_topics
    assert "mixing" in ans_topics or "ableton" in ans_topics

    # 3. Clarification in voice mode
    clarify_payload_single = clarification_payload("hello", answer_mode="voice")
    assert "1." not in clarify_payload_single["answer"]
    assert "clarify" in clarify_payload_single["route"]

    # Clarification repeat in voice mode
    history = [
        {"role": "user", "content": "unclear text"},
        {"role": "assistant", "content": "I can help, but I need one bit more direction first. Are you asking..."},
    ]
    clarify_payload_repeat = clarification_payload("unclear text", history=history, answer_mode="voice")
    assert "1." not in clarify_payload_repeat["answer"]
    assert "reset" in clarify_payload_repeat["answer"]

    # 4. Shortcut promise / impossible claim in voice mode
    unsupported_payload = impossible_promise_payload("secret settings to make vocals professional instantly", answer_mode="voice")
    assert "Short answer:" not in unsupported_payload["answer"]
    assert "1." not in unsupported_payload["answer"]
    assert "secret setting" in unsupported_payload["answer"]
