"""Unit and benchmark tests for KENN Studio Voice Control (VoiceCopilot)."""

from __future__ import annotations

import time
import pytest
from kenn.speech.voice_copilot import VoiceCopilot, get_voice_copilot


def test_speech_intent_extraction_accuracy():
    copilot = VoiceCopilot()
    test_cases = [
        ("KENN, audit the session and give me the mix health score", "AUDIT_SESSION"),
        ("How is my mix looking today?", "AUDIT_SESSION"),
        ("Unmask the kick and bass sub clash", "UNMASK_TRACKS"),
        ("Carve room for the lead vocal in the midrange", "UNMASK_TRACKS"),
        ("Are we clipping on the master bus?", "CHECK_HEADROOM"),
        ("What is my true peak reading right now?", "CHECK_HEADROOM"),
        ("Apply the proposed dynamic EQ recipe", "APPLY_REMEDY"),
        ("Confirm the parameter changes", "APPLY_REMEDY"),
        ("Toggle A/B audition so I can compare before and after", "AUDITION_TOGGLE"),
        ("Switch to original unprocessed mix", "AUDITION_TOGGLE"),
        ("Undo the last move immediately", "ATOMIC_UNDO"),
        ("Rollback the EQ cut", "ATOMIC_UNDO"),
    ]

    for phrase, expected_intent in test_cases:
        intent = copilot.classify_intent(phrase)
        assert intent.intent_type == expected_intent, f"Failed on '{phrase}': got {intent.intent_type}, expected {expected_intent}"
        assert intent.confidence >= 0.90
        assert intent.latency_ms < 50.0  # Must be sub-50ms parser


def test_voice_intent_end_to_end_latency():
    copilot = VoiceCopilot()
    latencies = []

    for _ in range(25):
        t0 = time.perf_counter()
        intent = copilot.classify_intent("KENN, check headroom and clipping")
        latencies.append((time.perf_counter() - t0) * 1000.0)

    avg_latency = sum(latencies) / len(latencies)
    assert avg_latency < 10.0, f"Average intent parse latency {avg_latency:.2f}ms exceeds 10ms target"



def test_voice_copilot_exposes_no_simulated_audio_pipeline() -> None:
    from kenn.speech.voice_copilot import VoiceCopilot

    assert not hasattr(VoiceCopilot, "process_audio_features")
