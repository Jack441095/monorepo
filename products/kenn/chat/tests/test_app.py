from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

import app  # noqa: E402


client = TestClient(app.app)


def setup_function() -> None:
    app.reset_rate_limit_for_tests()


def test_default_engine_root_is_the_canonical_product_backend() -> None:
    assert app.ENGINE_ROOT == SERVICE_ROOT.parent / "apps" / "backend" / "src"
    assert (app.ENGINE_ROOT / "kenn" / "core" / "chat.py").is_file()


def test_health_is_explicitly_retrieval_only() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert {key: payload[key] for key in (
        "status", "service", "scope", "llm_enabled", "audio_upload"
    )} == {
        "status": "ok",
        "service": "kenn-chat",
        "scope": "mix_advice_only",
        "llm_enabled": False,
        "audio_upload": False,
    }
    assert payload["retrieval"]["schema"] == "kenn.retrieval_status.v1"
    assert payload["retrieval"]["active_mode"] in {"unavailable", "bm25_only", "hybrid"}
    assert os.environ["AUDIO_TOO_LLM_ENABLED"] == "0"


def test_out_of_scope_is_abstained_before_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("out-of-scope request reached KENN engine")

    monkeypatch.setattr(app, "answer_payload", fail_if_called)
    response = client.post("/kenn/chat", json={"question": "Can you control my Ableton session?"})
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "out_of_scope"
    assert body["route"] == "out_of_scope"
    assert body["sources"] == []
    assert body["audio_uploaded"] is False


def test_upload_path_is_not_accepted() -> None:
    response = client.post("/kenn/chat", json={"question": "Upload my WAV and tell me what is wrong."})
    assert response.status_code == 200
    assert response.json()["intent"] == "out_of_scope"


@pytest.mark.parametrize(
    "question",
    [
        "Can you generate a mix for me?",
        "Can you create a mix?",
        "Can you render my mix?",
        "Can you automate my mix?",
        "Can you launch a clip in my mix?",
        "Can you control my DAW while I mix?",
        "Can you mix this for me?",
        "Can you fix my mix?",
        "Can you apply these mix changes?",
        "Can you process my mix?",
        "Can you review my mix?",
        "Which compressor is best for bass?",
        "What's the best EQ for vocals?",
        "Which plugin should I use for harshness?",
        "What limiter do you recommend for mastering?",
        "Which of these plugins is better for drums?",
        "Who invented mixing?",
        "Write lyrics for my mix.",
        "How much does a mix engineer charge?",
        "What is a mix engineer salary?",
        "Recommend a studio for my mix.",
        "Can you listen to this mix and tell me if it is good?",
        "Which compressor would you use for bass?",
        "What plugin do you prefer for vocals?",
    ],
)
def test_action_requests_with_mix_language_are_abstained_before_engine(
    monkeypatch: pytest.MonkeyPatch, question: str
) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("disallowed action request reached KENN engine")

    monkeypatch.setattr(app, "answer_payload", fail_if_called)
    response = client.post("/kenn/chat", json={"question": question})
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "out_of_scope"
    assert body["route"] == "out_of_scope"
    assert body["sources"] == []


def test_advice_wording_is_not_treated_as_direct_audio_action(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        app,
        "answer_payload",
        lambda *args, **kwargs: {
            "question": args[0],
            "answer": "Use a reference and check the low end in mono.",
            "sources": [{"source": "approved-note.md", "title": "Approved note", "kind": "note"}],
            "found": True,
            "weak_match": False,
            "confidence": "high",
            "source_quality": "high",
            "topics": ["mixing"],
            "intent": "troubleshooting",
            "route": "production",
            "answer_mode": "mix_diagnosis",
        },
    )
    response = client.post("/kenn/chat", json={"question": "How do I fix my mix?"})
    assert response.status_code == 200
    assert response.json()["found"] is True


def test_best_practice_advice_is_not_treated_as_plugin_ranking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        app,
        "answer_payload",
        lambda *args, **kwargs: {
            "question": args[0],
            "answer": "Check the relationship in mono before choosing a move.",
            "sources": [{"source": "approved-note.md", "title": "Approved note", "kind": "note"}],
            "found": True,
            "weak_match": False,
            "confidence": "high",
            "source_quality": "high",
            "topics": ["mixing"],
            "intent": "troubleshooting",
            "route": "production",
            "answer_mode": "mix_diagnosis",
        },
    )
    response = client.post("/kenn/chat", json={"question": "What is the best way to check mono compatibility?"})
    assert response.status_code == 200
    assert response.json()["found"] is True


def test_honest_no_audio_diagnostic_question_remains_text_advice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        app,
        "answer_payload",
        lambda *args, **kwargs: {
            "question": args[0],
            "answer": "I haven't actually heard your audio; compare the vocal in context.",
            "sources": [{"source": "approved-note.md", "title": "Approved note", "kind": "note"}],
            "found": True,
            "weak_match": False,
            "confidence": "high",
            "source_quality": "high",
            "topics": ["vocals"],
            "intent": "troubleshooting",
            "route": "production",
            "answer_mode": "mix_diagnosis",
        },
    )
    response = client.post(
        "/kenn/chat", json={"question": "Listen to my vocal and tell me exactly what is wrong with it."}
    )
    assert response.status_code == 200
    assert response.json()["found"] is True


def test_specialist_keyword_stays_retrieval_only() -> None:
    if not client.get("/health").json()["retrieval"]["available"]:
        pytest.skip("requires the approved local retrieval index")
    response = client.post(
        "/kenn/chat",
        json={
            "question": (
                "A narrow nasal frequency appears only on occasional vocal notes. "
                "Which frequency-dependent dynamics tool fits that problem?"
            )
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["sources"]
    answer = body["answer"].casefold()
    assert "ableton" not in answer
    assert "upload" not in answer


def test_broadcast_corpus_boundary_is_abstained() -> None:
    response = client.post(
        "/kenn/chat",
        json={
            "question": (
                "When can dialogue be used as the anchor element for long-form "
                "OTT loudness measurement?"
            )
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "out_of_scope"
    assert body["found"] is False
    assert body["sources"] == []


def test_ambiguous_question_abstains() -> None:
    response = client.post("/kenn/chat", json={"question": "Should I make it wider now?"})
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "out_of_scope"
    assert body["confidence"] == "low"


def test_request_rejects_audio_or_unknown_fields() -> None:
    response = client.post(
        "/kenn/chat",
        json={"question": "How do I fix vocal harshness?", "audio": "base64"},
    )
    assert response.status_code == 422


def test_public_payload_strips_source_document_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        app,
        "answer_payload",
        lambda *args, **kwargs: {
            "question": args[0],
            "answer": "Use a mono check and compare the relationship.",
            "sources": [
                {
                    "source": "phase-and-polarity-checks.md",
                    "page": 0,
                    "kind": "note",
                    "title": "Phase and polarity checks",
                    "score": 8.1,
                    "trust_score": 0.9,
                    "label": "Phase and polarity checks",
                    "text": "Private indexed note text must not leave the service.",
                }
            ],
            "found": True,
            "weak_match": False,
            "confidence": "high",
            "source_quality": "high",
            "topics": ["stereo_width"],
            "intent": "troubleshooting",
            "route": "production",
            "answer_mode": "mix_diagnosis",
            "diagnostic_reason": "grounded",
        },
    )
    response = client.post("/kenn/chat", json={"question": "My mix collapses in mono."})
    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["sources"][0]["source"] == "phase-and-polarity-checks.md"
    assert "text" not in body["sources"][0]


def test_rate_limit_returns_429(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.RATE_LIMITER, "max_requests", 1)
    monkeypatch.setattr(
        app,
        "answer_mix_question",
        lambda question, history=None: {"intent": "out_of_scope", "question": question},
    )
    first = client.post("/kenn/chat", json={"question": "How do I fix vocal harshness?"})
    second = client.post("/kenn/chat", json={"question": "How do I fix vocal harshness?"})
    assert first.status_code == 200
    assert second.status_code == 429
