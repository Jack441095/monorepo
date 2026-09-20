"""Comprehensive unit & scenario tests for KENN Foolproof Studio Chatbot."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.core.chat_formatting import weak_match_answer
from kenn.core.chat_routing import conversational_intent, conversational_payload


def test_conversational_greetings_no_disclaimers():
    """Verify small-talk phrases return conversational payloads without error disclaimers."""
    greetings = [
        "Hey, all right, how you doing?",
        "How are you doing today?",
        "Hey KENN, what's good?",
        "Good morning!",
        "Yo, how's it going?",
    ]
    for phrase in greetings:
        intent = conversational_intent(phrase)
        assert intent in ("greeting", "check_in"), f"Failed intent check for '{phrase}': got '{intent}'"

        payload = conversational_payload(phrase)
        assert payload is not None, f"Failed payload check for '{phrase}'"
        assert payload["conversation_only"] is True
        assert "do not have a clear audio-production topic" not in payload["answer"]
        assert len(payload["answer"]) > 10


def test_weak_match_answer_warmth():
    """Verify weak_match_answer returns warm, helpful text without cold disclaimers."""
    ans_out_of_scope = weak_match_answer("what is the recipe for sourdough bread")
    assert "do not have a clear audio-production topic" not in ans_out_of_scope
    assert "I am not going to guess" not in ans_out_of_scope
    assert "I specialize in audio engineering" in ans_out_of_scope

    ans_general = weak_match_answer("tell me something cool")
    assert "do not have a clear audio-production topic" not in ans_general
    assert "I am not going to guess" not in ans_general
    assert len(ans_general) > 10


def test_conversational_thanks_and_meta():
    """Verify thanks and meta questions return friendly, engaging payloads."""
    for phrase in ["thanks a lot!", "cheers mate", "who are you?", "what can you do"]:
        intent = conversational_intent(phrase)
        assert intent in ("thanks", "meta", "help"), f"Failed intent for '{phrase}': got '{intent}'"
        payload = conversational_payload(phrase)
        assert payload is not None
        assert payload["conversation_only"] is True
        assert len(payload["answer"]) > 10


def test_session_memory_sync_with_thursday():
    """Verify updating session memory correctly syncs with Thursday MemoryManager."""
    from kenn.core.session_memory import update_session
    from thursday.memory.memory_manager import get_memory_manager

    state = update_session(
        query="How do I tame sibilance on Lead Vocal in Project Solar?",
        answer="Use a dynamic de-esser focused around 6 kHz with 3 dB gain reduction.",
        route="production",
        answer_mode="mix_diagnosis",
        session_id="test_sync_session",
    )
    assert state["session_id"] == "test_sync_session"
    assert "vocals" in state["topics_mentioned"] or "de-essing" in state["techniques_mentioned"]

    mm = get_memory_manager()
    episodes = mm.episodic_memory.query_episodes("sibilance")
    assert len(episodes) > 0, "Expected episode to be synced into Thursday MemoryManager"


def test_casual_banter_and_jokes():
    """Verify jokes and casual banter return natural conversational answers."""
    intent = conversational_intent("tell me a producer joke")
    assert intent == "joke"
    payload = conversational_payload("tell me a producer joke")
    assert payload is not None
    assert "engineer" in payload["answer"].lower() or "analog" in payload["answer"].lower() or "lightbulb" in payload["answer"].lower() or "pizza" in payload["answer"].lower()


def test_thursday_no_dead_end_missing_info_error():
    """Verify Thursday handles casual inputs without returning 'I need current_mix_review...' errors."""
    from thursday.orchestrator import handle

    res = handle("Hey, Thursday. Can you tell Jasmine that her horses suck?")
    assert "I need current_mix_review to look that up" not in res
    assert len(res) > 10
