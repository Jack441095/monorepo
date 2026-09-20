from __future__ import annotations

from nite_core import AssistantResponse, ResultEnvelope
from kenn.core.response_contract import augment_payload


def test_kenn_payload_retains_legacy_fields_and_adds_canonical_envelope() -> None:
    legacy = {
        "answer": "Use a shorter release and verify at matched loudness.",
        "intent": "troubleshooting",
        "route": "production",
        "confidence": "high",
        "grounding": {"score": 91, "mode": "strong"},
        "sources": [{"label": "Sidechain Bass To Kick", "source": "sidechain.md"}],
        "related_questions": ["How should I set attack?"],
        "answer_mode": "mix_diagnosis",
        "weak_match": False,
    }

    payload = augment_payload(
        legacy,
        question="Why is my sidechain pumping?",
        session_id="kenn-session-1",
        correlation_id="http-request-1",
    )

    assert payload["answer"] == legacy["answer"]
    assert payload["correlation_id"] == "http-request-1"
    envelope = ResultEnvelope.from_dict(payload["envelope"])
    assistant = AssistantResponse.from_dict(
        {key: value for key, value in envelope.result.items() if key != "capability"}
    )
    assert envelope.result["capability"] == "kenn.ask"
    assert assistant.service == "kenn"
    assert assistant.session_id == "kenn-session-1"
    assert assistant.grounding["score"] == 91
    assert assistant.suggestions == ({"label": "How should I set attack?"},)
