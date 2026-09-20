from __future__ import annotations

from nite_core import AssistantResponse, ResultEnvelope
from thursday import main as thursday_main
from thursday import orchestrator, session_manager, voice
from thursday.bridge import ask, ask_stream
from thursday.command_gateway import AssistantResultText
from thursday.intent import classify_intent


BASE_QUESTIONS = (
    "how's business",
    "tell me about Jordan",
    "show invoices",
    "what's on my calendar",
    "generate a joyful loop",
    "analyse my mix",
    "how should I compress a vocal",
    "run a system health check",
    "draft email to Jordan",
    "search for project alpha",
)
VARIANTS = (
    "",
    " please",
    " now",
    " for me",
    " today",
    " when ready",
    " and be concise",
    " with the key details",
    " as a quick check",
    " using the current records",
)
PARITY_QUESTIONS = tuple(base + suffix for base in BASE_QUESTIONS for suffix in VARIANTS)

SERVICE_BY_INTENT = {
    "business_ops": "business_status",
    "client_mgmt": "client_info",
    "financial": "invoices",
    "calendar_scheduling": "calendar",
    "audio_generation": "audiogen",
    "mix_review_audio_analysis": "audio_analysis",
    "production_qa": "kenn",
    "system_diagnostics": "diagnostics",
    "agent_tasks": "admin_agent",
    "search": "search",
}


def _assistant(result_dict: dict) -> AssistantResponse:
    envelope = ResultEnvelope.from_dict(result_dict)
    return AssistantResponse.from_dict(
        {key: value for key, value in envelope.result.items() if key != "capability"}
    )


def test_one_hundred_requests_keep_semantics_across_sync_stream_cli_and_voice(
    tmp_path,
    monkeypatch,
) -> None:
    from kenn.core import chat

    assert len(PARITY_QUESTIONS) == 100
    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / "current")

    def answer_for(text: str) -> str:
        return f"Handled consistently: {text}"

    def fake_handle(text: str, session: dict | None = None, **_kwargs) -> str:
        intent = classify_intent(text, (session or {}).get("context", {})).name
        if session is not None:
            service = SERVICE_BY_INTENT.get(intent, "unknown")
            session_manager.add_turn(session, "user", text, intent, service, {})
            session_manager.add_turn(session, "thursday", answer_for(text), intent, service, {})
        if intent == "production_qa":
            return AssistantResultText(
                answer_for(text),
                {
                    "route": "production",
                    "confidence": "high",
                    "grounding": {"score": 90},
                    "sources": ({"label": "Approved test source"},),
                },
            )
        if intent == "audio_generation":
            return AssistantResultText(
                answer_for(text),
                {
                    "requires_confirmation": True,
                    "confirmation_token": f"confirm-{len(text)}",
                    "metadata": {
                        "confirmation_risk": "local_mutation",
                        "confirmation_service": "audiogen",
                    },
                },
            )
        return answer_for(text)

    def fake_kenn_stream(question: str, **_kwargs):
        yield {
            "event": "metadata",
            "data": {
                "route": "production",
                "confidence": "high",
                "grounding": {"score": 90},
                "sources": [{"label": "Approved test source"}],
            },
        }
        yield {"event": "token", "token": answer_for(question)}

    monkeypatch.setattr(orchestrator, "handle", fake_handle)
    monkeypatch.setattr(thursday_main, "handle", fake_handle)
    monkeypatch.setattr(chat, "answer_payload_stream", fake_kenn_stream)

    for index, question in enumerate(PARITY_QUESTIONS):
        sync = ask(question, session_id=f"sync-{index}")
        stream_events = list(ask_stream(question, session_id=f"stream-{index}"))
        stream = next(event["data"] for event in stream_events if event["event"] == "metadata")

        cli_session = session_manager.get_or_create_session(f"cli-{index}")
        cli = thursday_main.execute_cli_request(question, cli_session)
        voice_session = session_manager.get_or_create_session(f"voice-{index}")
        voice_result = voice.execute_voice_command_result(question, voice_session, fake_handle)

        responses = (
            _assistant(sync["envelope"]),
            _assistant(stream["envelope"]),
            _assistant(cli.to_dict()),
            _assistant(voice_result.to_dict()),
        )
        expected = responses[0]
        for response in responses[1:]:
            assert response.answer == expected.answer
            assert response.intent == expected.intent
            assert response.service == expected.service
            assert response.route == expected.route
            assert response.confidence == expected.confidence
            assert response.grounding == expected.grounding
            assert response.sources == expected.sources
            assert response.requires_confirmation == expected.requires_confirmation
            assert response.confirmation_token == expected.confirmation_token
