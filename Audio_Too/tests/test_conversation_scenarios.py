"""Unit and integration tests for KENN conversation scenarios: topic changes, corrections, pronouns, and returning sessions."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.core.chat_routing import (
    should_use_history,
    route_query,
)
from kenn.core.session_memory import load_session, update_session, build_session_context


def test_pronoun_reference_resolves_via_history() -> None:
    # First turn: User asks about muddy vocals
    history = [
        {"role": "user", "content": "How do I fix muddy vocals?"},
        {"role": "assistant", "content": "Short answer: Use a high pass filter."},
    ]
    # Follow-up: User asks "how do I automate it?" which has pronoun "it"
    assert should_use_history("how do I automate it?", history) is True
    assert should_use_history("explain that more", history) is True


def test_elliptical_what_x_should_i_question_uses_history() -> None:
    """Regression (2026-08-02, live-tested): "should i"/"do i"/"can i" are
    recognized follow-up starters, but only when they open the sentence --
    "what release time should I use?" (an obvious elliptical follow-up to a
    sidechain-compression question just asked) has "should i" mid-sentence,
    after the short "release time" noun phrase, so it fell through every
    check and was treated as a fresh, context-free query. Retrieval then
    matched "release" to an unrelated arrangement/EDM note instead of the
    compression parameter the user obviously meant."""
    history = [
        {"role": "user", "content": "how do I sidechain bass to the kick?"},
        {"role": "assistant", "content": "Short answer: use a compressor with the kick as the sidechain input."},
    ]
    assert should_use_history("what release time should I use?", history) is True
    assert should_use_history("what ratio should I use?", history) is True
    assert should_use_history("what attack time do I need?", history) is True


def test_and_if_followup_uses_history() -> None:
    """Regression (2026-08-03, live-tested): "and what"/"and how" were
    already recognized follow-up starters, but "and if" was not. Asked
    "how do i warp audio in ableton" then "what about when the tempo
    changes mid song" then "and if the transients get smeared" -- the third
    turn is an obvious elliptical follow-up about warp-induced transient
    smearing, but with "and if" unrecognized, is_followup_query() returned
    False, history was dropped, and retrieval matched generic drum/crest-
    factor content instead of the warp-modes note the conversation was
    actually about."""
    history = [
        {"role": "user", "content": "how do i warp audio in ableton"},
        {"role": "assistant", "content": "Short answer: use warp markers to fix timing."},
    ]
    assert should_use_history("and if the transients get smeared", history) is True
    assert should_use_history("what if the transients get smeared", history) is True


def test_topic_change_does_not_leak_unrelated_context() -> None:
    # First turn: User asks about vocal recording
    history = [
        {"role": "user", "content": "What is the best mic for recording vocals?"},
        {"role": "assistant", "content": "Short answer: Use a condenser microphone."},
    ]
    # User shifts topic to Wwise SoundBanks. This is a topic change.
    # It is not a followup query on vocals, so should_use_history should be False.
    assert should_use_history("how do I build SoundBanks in Wwise?", history) is False


def test_returning_session_loads_correct_state(tmp_path, monkeypatch) -> None:
    # Mock KENN_CHATS_DIR to use temporary path
    monkeypatch.setenv("KENN_CHATS_DIR", str(tmp_path))
    monkeypatch.setenv("KENN_DB_PATH", str(tmp_path / "kenn.db"))
    
    session_id = "test_returning_session_id"
    
    # Simulate first turn
    update_session(
        query="How do I EQ snare?",
        answer="Short answer: cut the mud at 250 Hz.",
        route="production",
        answer_mode="mix_diagnosis",
        confidence="high",
        session_id=session_id,
    )
    
    # Simulate second turn
    update_session(
        query="Should I automate send levels?",
        answer="Short answer: yes, automate them.",
        route="production",
        answer_mode="mix_diagnosis",
        confidence="high",
        session_id=session_id,
    )
    
    # Reload session as a "returning session"
    reloaded = load_session(session_id=session_id)
    assert reloaded["session_id"] == session_id
    assert reloaded["turn_count"] == 2
    assert reloaded["last_question"] == "Should I automate send levels?"
    
    # Context builder checks
    context = build_session_context(reloaded, session_id=session_id)
    assert "EQ" in context or "drums" in context or "sends" in context
    assert "Did that change help the symptom?" in context
    assert "Did that change help the symptom?" in context


def test_correction_updates_route_and_state(tmp_path, monkeypatch) -> None:
    # Mock KENN_CHATS_DIR to use temporary path
    monkeypatch.setenv("KENN_CHATS_DIR", str(tmp_path))
    monkeypatch.setenv("KENN_DB_PATH", str(tmp_path / "kenn.db"))

    session_id = "correction_session"

    # User asks something that was routed to Ableton
    update_session(
        query="How do I route track in Live?",
        answer="Use track IO routing.",
        route="ableton",
        session_id=session_id,
    )

    # User corrects: "No, I meant in Wwise"
    corrected_route = route_query("No, I meant in Wwise", history=[
        {"role": "user", "content": "How do I route track in Live?"},
        {"role": "assistant", "content": "Use track IO routing."},
    ])

    # Route should correctly adapt to game_audio because of "Wwise"
    assert corrected_route == "game_audio"


def test_greeting_and_checkin_conversational_intents() -> None:
    from kenn.core.chat_routing import conversational_intent, conversational_payload

    for phrase in [
        "Hey, all right, how you doing?",
        "Hey man, how's it going?",
        "Hi, how are you today?",
        "Yo, good morning!",
    ]:
        intent = conversational_intent(phrase)
        assert intent in ("greeting", "check_in"), f"Expected conversational intent for '{phrase}', got '{intent}'"

        payload = conversational_payload(phrase)
        assert payload is not None, f"Expected non-None payload for '{phrase}'"
        assert payload["conversation_only"] is True
        assert len(payload["answer"]) > 0
