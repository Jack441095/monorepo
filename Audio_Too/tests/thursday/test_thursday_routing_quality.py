from __future__ import annotations

import pytest

from thursday.intent import classify_intent
from thursday.orchestrator import classify_request


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Hey Thursday, how is business?", "business_ops"),
        ("What does my day look like?", "calendar_scheduling"),
        ("How much revenue did mixing make?", "financial"),
        ("Tell me about client Jordan", "client_mgmt"),
        ("Could you send me to Ken please?", "kenn_voice_mode"),
        # Regression: a filler word ("over") between "send me" and "to kenn"
        # used to make every kenn_voice_mode pattern miss, so this fell
        # through to production_qa (triggered by the unrelated "send"
        # audio-routing term) and forwarded the raw handoff phrase to KENN's
        # answer pipeline as if it were a real question.
        ("You send me over to Ken, please", "kenn_voice_mode"),
        ("send me on to kenn", "kenn_voice_mode"),
        ("Why is my vocal harsh after compression?", "production_qa"),
        ("Generate a dark eight-bar loop", "audio_generation"),
        ("Analyse my mix", "mix_review_audio_analysis"),
        # 2026-08-07: weather is now a real service (utility_tools.py,
        # Open-Meteo), not generic chit-chat -- see
        # test_thursday_upgrade.py::test_weather_is_a_real_intent_not_generic_chitchat.
        ("What is the weather tomorrow?", "weather"),
        ("How can I improve my website copy?", "unknown"),
        # Regression (2026-07-27): bare "session(s)" beat production_qa's
        # "mixing" trigger on weight alone, so a production question about a
        # "mixing session" misrouted into client_mgmt's "No sessions
        # recorded yet." Genuine business-session phrasing must still work.
        ("staying creative during a long mixing session", "production_qa"),
        ("why is my recording session so quiet", "unknown"),
        ("list my sessions", "client_mgmt"),
        ("show upcoming sessions", "client_mgmt"),
        ("what sessions do I have", "client_mgmt"),
    ],
)
def test_adversarial_routing_matrix(question: str, expected: str) -> None:
    assert classify_intent(question).name == expected


def test_canonical_decision_owns_streaming_target() -> None:
    session = {"session_id": "routing-test", "context": {}, "turns": []}
    production = classify_request("how should I compress a vocal?", session)
    business = classify_request("how's business?", session)

    assert production.intent.name == "production_qa"
    assert production.execution_target == "kenn_stream"
    assert business.intent.name == "business_ops"
    assert business.execution_target == "orchestrator"
