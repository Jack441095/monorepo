"""A symptom plan survives weak retrieval over the chat stream, as it does without streaming (30 Sept 2026)."""

from __future__ import annotations

from kenn.core import chat_answer, chat_retrieval

QUESTION = "How does the live bus compare with my uploaded reference?"


def _no_index(monkeypatch) -> None:
    # No notes at all, so retrieval is as weak as it gets; a fresh clone has exactly this.
    terms = {"total_docs": 0, "avg_len": 1.0, "lengths": [], "idf": {}, "postings": {}}
    for module in (chat_retrieval, chat_answer):
        monkeypatch.setattr(module, "load_chunks", lambda: [], raising=False)
        monkeypatch.setattr(module, "load_terms", lambda: terms, raising=False)
        monkeypatch.setattr(module, "search", lambda *args, **kwargs: [], raising=False)


def _stream_answer(**kwargs) -> tuple[str, dict]:
    events = list(chat_answer.answer_payload_stream(QUESTION, allow_llm=False, **kwargs))
    metadata = [event["data"] for event in events if event.get("event") == "metadata"][-1]
    text = "".join(event.get("token", "") for event in events if event.get("event") == "token")
    return text, metadata


def test_the_stream_keeps_the_symptom_plan_when_retrieval_finds_nothing(monkeypatch) -> None:
    _no_index(monkeypatch)
    text, metadata = _stream_answer()
    assert text.startswith("Diagnosis first:")
    # Weak retrieval still drops the sources and says so.
    assert metadata["found"] is False and metadata["sources"] == [] and metadata["weak_match"] is True


def test_the_stream_and_the_plain_answer_agree_on_a_symptom_plan(monkeypatch) -> None:
    _no_index(monkeypatch)
    plain = chat_answer.answer_payload(QUESTION, allow_llm=False)
    text, _ = _stream_answer()
    assert plain["answer"].startswith("Diagnosis first:") and text.startswith("Diagnosis first:")


def test_the_stream_still_withholds_a_question_with_no_plan_and_no_notes(monkeypatch) -> None:
    _no_index(monkeypatch)
    events = list(chat_answer.answer_payload_stream("tell me about the mating habits of owls", allow_llm=False))
    metadata = [event["data"] for event in events if event.get("event") == "metadata"][-1]
    assert metadata["found"] is False
    assert not "".join(e.get("token", "") for e in events if e.get("event") == "token").startswith("Diagnosis first:")
