import pytest

from kenn.core import chat_answer, chat_retrieval
from kenn.core.chat_routing import (
    history_context_line,
    is_correction_query,
    is_followup_query,
    search_query_with_history,
    should_use_history,
)

HISTORY = [
    {"role": "user", "content": "My vocal sounds muddy in the mix."},
    {"role": "assistant", "content": "Try a cut in the low mids on the vocal."},
    {"role": "user", "content": "Which frequencies should I look at?"},
    {"role": "assistant", "content": "Look at 200 to 400 Hz."},
]


@pytest.mark.parametrize(
    "query",
    [
        "Sorry, it is the acoustic guitar that is muddy, not the vocal.",
        "No, on the drum bus instead.",
        "I meant the snare, not the kick.",
        "Actually it's the bass.",
    ],
)
def test_a_correction_is_a_follow_up_that_uses_the_chat(query) -> None:
    assert is_correction_query(query)
    assert should_use_history(query, HISTORY)


@pytest.mark.parametrize(
    "query",
    [
        "No problem, thanks.",
        "How do I stop my kick being muddy, not boomy?",
        "Not sure what a limiter does.",
    ],
)
def test_ordinary_questions_and_thanks_are_not_corrections(query) -> None:
    assert not is_correction_query(query)
    assert not should_use_history(query, HISTORY)


def test_and_the_attack_carries_the_previous_question() -> None:
    assert is_followup_query("And the attack?")
    assert search_query_with_history("And the attack?", HISTORY).startswith("Which frequencies")


def test_the_search_for_a_correction_keeps_the_original_problem_and_drops_what_was_ruled_out() -> None:
    # 3 Oct 2026: this was searched on its own, so "muddy" and the whole conversation were lost.
    searched = search_query_with_history("Sorry, it is the acoustic guitar that is muddy, not the vocal.", HISTORY)

    assert "My vocal sounds muddy" in searched
    assert "acoustic guitar" in searched
    assert not searched.endswith("not the vocal.")
    assert "the vocal." not in searched.split("Which frequencies")[1]


def test_the_model_is_told_it_is_a_correction() -> None:
    assert history_context_line("No, on the drum bus instead.", HISTORY).startswith("[Correction]")


@pytest.mark.parametrize("stream", [False, True], ids=["payload", "stream"])
def test_correcting_the_muddy_instrument_keeps_chat_history_instead_of_dispatching_live(stream, monkeypatch, tmp_path) -> None:
    # 3 Oct 2026: the raw correction reached the Live translator before history-aware routing.
    monkeypatch.setenv("KENN_CHATS_DIR", str(tmp_path / "chats"))
    monkeypatch.setenv("KENN_DB_PATH", str(tmp_path / "kenn.db"))
    monkeypatch.setattr(chat_answer, "latest_track_memory_lookup", lambda query: None)
    terms = {"total_docs": 0, "avg_len": 1.0, "lengths": [], "idf": {}, "postings": {}}
    for module in (chat_answer, chat_retrieval):
        monkeypatch.setattr(module, "load_chunks", lambda: [])
        monkeypatch.setattr(module, "load_terms", lambda: terms)
        monkeypatch.setattr(module, "search", lambda *args, **kwargs: [])
    orchestrator = chat_answer.get_orchestrator()
    dispatched = []

    def dispatch(query, **kwargs):
        agent = orchestrator.classify(query)
        dispatched.append(agent)
        return {"agent_name": agent, "message": "Canned Live reply"} if agent else None

    monkeypatch.setattr(orchestrator, "dispatch", dispatch)
    query = "Sorry, it is the acoustic guitar that is muddy, not the vocal."
    if stream:
        events = list(chat_answer.answer_payload_stream(query, history=HISTORY, allow_llm=False))
        payload = [event["data"] for event in events if event["event"] == "metadata"][-1]
    else:
        payload = chat_answer.answer_payload(query, history=HISTORY, allow_llm=False)

    assert payload["route"] != "ableton_controller"
    assert payload["used_history"]
    assert "acoustic guitar" in payload["search_query"]
    assert "My vocal sounds muddy" in payload["search_query"]
    assert dispatched == []
