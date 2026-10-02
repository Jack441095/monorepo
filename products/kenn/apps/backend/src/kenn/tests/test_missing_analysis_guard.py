import pytest

from kenn.core import chat_answer
from kenn.core.chat_routing import asks_about_unrun_analysis

ANALYSIS_TURN = [
    {"role": "user", "content": "How did the analysis of my mix go?"},
    {"role": "assistant", "content": "I haven't analysed a mix in this chat."},
]


@pytest.fixture(autouse=True)
def isolated_stores(monkeypatch, tmp_path):
    monkeypatch.setenv("KENN_CHATS_DIR", str(tmp_path / "chats"))
    monkeypatch.setenv("KENN_DB_PATH", str(tmp_path / "kenn.db"))
    monkeypatch.setattr(chat_answer, "latest_track_memory_lookup", lambda query: None)


@pytest.mark.parametrize(
    "query",
    [
        "How did the analysis of my mix go?",
        "what came out of the scan on my drums",
        "What were the results of the mix review?",
        "Can you re-run the analysis?",
    ],
)
def test_wording_that_assumes_a_finished_analysis_is_caught(query) -> None:
    assert asks_about_unrun_analysis(query)


@pytest.mark.parametrize(
    "query",
    [
        "How is spectral analysis used in EQ?",
        "How do I check my mix in mono?",
        "Run it again.",
    ],
)
def test_a_knowledge_question_or_a_bare_rerun_with_nothing_to_rerun_is_left_alone(query) -> None:
    assert not asks_about_unrun_analysis(query)


def test_a_bare_rerun_counts_once_an_earlier_turn_was_about_an_analysis() -> None:
    assert asks_about_unrun_analysis("Run it again.", ANALYSIS_TURN)


def test_asking_how_an_analysis_went_with_none_run_says_so_instead_of_describing_one() -> None:
    # 3 Oct 2026: the model answered this from retrieved notes as if an analysis had run, with a cited -18 dB.
    payload = chat_answer.answer_payload("How did the analysis of my mix go?", allow_llm=False)

    assert payload["route"] == "no_analysis"
    assert payload["sources"] == []
    assert "haven't analysed a mix" in payload["answer"]


def test_the_stream_path_gives_the_same_honest_answer() -> None:
    events = list(chat_answer.answer_payload_stream("How did the analysis of my mix go?", allow_llm=False))

    metadata = [event["data"] for event in events if event["event"] == "metadata"]
    assert metadata[-1]["route"] == "no_analysis"
    assert not any(event.get("event") == "token" and "18" in event["token"] for event in events)


def test_a_rerun_request_in_a_chat_with_no_analysis_is_not_pretended() -> None:
    payload = chat_answer.answer_payload("Run it again.", history=ANALYSIS_TURN, allow_llm=False)

    assert payload["route"] == "no_analysis"


def test_a_real_mix_review_in_the_history_is_still_answered_from_it() -> None:
    history = [
        {"role": "user", "content": "Mix Review Lab context: Structured priority actions: cut 250 Hz mud on the guitars"},
    ]

    payload = chat_answer.answer_payload("How did the analysis of my mix go?", history=history, allow_llm=False)

    assert payload["route"] != "no_analysis"
