from __future__ import annotations

from nite_core import AssistantResponse, ResultEnvelope
from thursday import session_manager
from thursday.bridge import ask_stream


def test_kenn_stream_persists_complete_answer_and_emits_envelope(tmp_path, monkeypatch) -> None:
    from kenn.core import chat

    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / "current")

    def fake_stream(*_args, **_kwargs):
        yield {
            "event": "metadata",
            "data": {
                "route": "production",
                "confidence": "high",
                "grounding": {"score": 92},
                "sources": [{"label": "Sidechain Bass To Kick"}],
            },
        }
        yield {"event": "token", "token": "Set the release "}
        yield {"event": "token", "token": "to recover before the next kick."}

    monkeypatch.setattr(chat, "answer_payload_stream", fake_stream)
    events = list(
        ask_stream(
            "How do I sidechain bass to a kick?",
            session_id="stream-1",
            request_id="http-stream-1",
        )
    )

    assert [event["event"] for event in events] == ["token", "token", "metadata", "done"]
    metadata = events[-2]["data"]
    assert metadata["answer"] == "Set the release to recover before the next kick."
    assert metadata["correlation_id"] == "http-stream-1"
    assert metadata["request_id"] != metadata["correlation_id"]
    envelope = ResultEnvelope.from_dict(metadata["envelope"])
    assistant = AssistantResponse.from_dict(
        {key: value for key, value in envelope.result.items() if key != "capability"}
    )
    assert assistant.answer == metadata["answer"]
    assert assistant.service == "kenn"
    assert assistant.confidence.value == "high"

    stored = session_manager.load_session("stream-1")
    assert stored is not None
    assistant_turn = stored["turns"][-1]
    assert assistant_turn["role"] == "thursday"
    assert "recover before the next kick" in assistant_turn["text"]


def test_non_kenn_stream_uses_same_envelope_as_sync_response(tmp_path, monkeypatch) -> None:
    from thursday import client, monitor

    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / "current")
    monkeypatch.setattr(monitor, "ALERTS_DIR", tmp_path / "alerts")
    monkeypatch.setattr(client, "business_status", lambda *_args: "Business is healthy.")

    events = list(
        ask_stream(
            "how's business",
            session_id="stream-business",
            request_id="http-business-1",
        )
    )

    assert [event["event"] for event in events] == ["token", "metadata", "done"]
    metadata = events[1]["data"]
    assert events[0]["token"] == metadata["answer"]
    assert events[0]["request_id"] == metadata["request_id"] == events[2]["request_id"]
    assert metadata["correlation_id"] == "http-business-1"
    assert ResultEnvelope.from_dict(metadata["envelope"]).result["service"] == metadata["service"]
