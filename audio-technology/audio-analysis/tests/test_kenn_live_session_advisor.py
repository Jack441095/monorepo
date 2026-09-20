"""Stage L (near-term MVP) — live in-DAW session advisor tests.

explain_live_session_state() (audio_analysis.integration.kenn_handoff) is
the only Python-side entry point for a Max for Live device to ask KENN about
a live track's current state. These tests mock
kenn.core.chat_answer.answer_payload directly (no real KENN index required)
to verify question-building and payload stamping, matching the pattern
already used in test_kenn_dynamic_eq_explanations.py for testing this
module's plumbing without depending on a built index.
"""

from __future__ import annotations

from unittest.mock import patch

from audio_analysis.integration.kenn_handoff import (
    build_live_session_question,
    explain_live_session_state,
)


def test_question_includes_track_device_chain_and_params() -> None:
    question = build_live_session_question(
        track_name="Lead Vocal",
        device_chain=["EQ Eight", "Compressor"],
        key_params={"Compressor.Ratio": "4:1"},
        genre="pop",
    )
    assert "Lead Vocal" in question
    assert "pop" in question
    assert "EQ Eight" in question and "Compressor" in question
    assert "Compressor.Ratio=4:1" in question


def test_question_omits_optional_clauses_when_absent() -> None:
    question = build_live_session_question(track_name="Bass")
    assert "Bass" in question
    assert "device chain" not in question
    assert "Key parameter values" not in question


def test_explain_live_session_state_uses_the_shared_answer_pipeline() -> None:
    captured = {}

    def fake_answer_payload(question, limit=4, history=None, *, allow_llm=True, profile=False, session_id=""):
        captured["question"] = question
        captured["session_id"] = session_id
        return {"answer": "Try a gentle high-pass around 100 Hz.", "sources": ["note.md"], "weak_match": False, "found": True}

    with patch("kenn.core.chat_answer.answer_payload", side_effect=fake_answer_payload):
        result = explain_live_session_state(
            track_name="Kick",
            device_chain=["Saturator"],
            key_params={"Saturator.Drive": "3dB"},
            genre="edm",
            session_id="abc123",
        )

    assert "Kick" in captured["question"]
    assert captured["session_id"] == "abc123"
    assert result["live_track_name"] == "Kick"
    assert result["live_device_chain"] == ["Saturator"]
    assert result["live_key_params"] == {"Saturator.Drive": "3dB"}
    assert result["answer"] == "Try a gentle high-pass around 100 Hz."


def test_weak_match_is_passed_through_untouched() -> None:
    """A low-confidence KENN answer must reach the caller labeled weak_match,
    not be silently upgraded to a confident-looking suggestion (Stage L §L4's
    'should say so rather than guess' rule)."""
    def fake_answer_payload(question, limit=4, history=None, *, allow_llm=True, profile=False, session_id=""):
        return {"answer": "Not confident.", "sources": [], "weak_match": True, "found": False}

    with patch("kenn.core.chat_answer.answer_payload", side_effect=fake_answer_payload):
        result = explain_live_session_state(track_name="Synth Pad")

    assert result["weak_match"] is True
    assert result["found"] is False
