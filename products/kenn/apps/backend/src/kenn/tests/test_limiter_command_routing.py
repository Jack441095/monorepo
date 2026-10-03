import pytest

from kenn.core import chat_answer, chat_retrieval, live_command, live_receipt_journal
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.orchestrator import get_orchestrator


@pytest.mark.parametrize("stream", [False, True], ids=["payload", "stream"])
@pytest.mark.parametrize("verb", ["Put", "Add", "Insert"])
def test_limiter_insertion_gets_an_honest_refusal_without_model_advice(stream, verb, monkeypatch, tmp_path) -> None:
    # 3 Oct 2026: "put a limiter" fell through to knowledge generation instead of the command gateway.
    monkeypatch.setenv("KENN_CHATS_DIR", str(tmp_path / "chats"))
    monkeypatch.setenv("KENN_DB_PATH", str(tmp_path / "kenn.db"))
    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    backend = FakeLiveBackend()
    service = LiveActionService(backend)
    monkeypatch.setattr(live_command, "LiveActionService", lambda: service)

    def unexpected_advice(*args, **kwargs):
        pytest.fail("A limiter insertion request must stop at the deterministic command gateway")

    for module in (chat_answer, chat_retrieval):
        monkeypatch.setattr(module, "load_chunks", unexpected_advice)
        monkeypatch.setattr(module, "search", unexpected_advice)
    monkeypatch.setattr(chat_answer, "llm_enhance_answer", unexpected_advice)
    monkeypatch.setattr(chat_answer, "llm_enhance_answer_stream", unexpected_advice)
    query = f"{verb} a limiter on the master for me."
    if stream:
        events = list(chat_answer.answer_payload_stream(query, session_id="limiter-command"))
        payload = [event["data"] for event in events if event["event"] == "metadata"][-1]
    else:
        payload = chat_answer.answer_payload(query, session_id="limiter-command")

    assert payload["route"] == "ableton_controller"
    assert "KENN can't add Limiter yet" in payload["answer"]
    assert not payload["llm_enhanced"]
    result = payload["orchestration"]["result"]
    assert result["changed"] is False
    assert not result.get("proposal")
    assert not payload.get("proposal")
    assert not payload.get("requires_confirmation")
    assert backend.writes == []


@pytest.mark.parametrize("query", [
    "How do I put a limiter on the master?",
    "Should I add a limiter to the drum bus?",
    "What does a limiter do?",
])
def test_limiter_advice_questions_stay_out_of_live_command_dispatch(query) -> None:
    assert get_orchestrator().classify(query) is None
