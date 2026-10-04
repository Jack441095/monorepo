"""Off-topic asks are declined in one polite line that points back at what KENN does."""

import re

import pytest

from kenn.core import chat_answer, chat_retrieval
from kenn.core.chat_formatting import weak_match_answer
from kenn.core.chat_retrieval import off_topic_kind, query_is_out_of_scope
from kenn.core.chat_routing import route_query


@pytest.mark.parametrize("query", [
    "what is the best lasagna recipe for dinner tonight",
    "can you debug my Python script that crashes on line 42",
    "who should i vote for in the upcoming election",
    "how do i fix the brakes on my car",
    "do my algebra homework and solve these 10 equations",
    "what stocks should i buy to get rich fast",
    "write my dating profile bio to get more matches",
    "can you book my band a tour across 12 concert venues",
])
def test_a_request_with_nothing_to_do_with_audio_is_declined(query):
    assert query_is_out_of_scope(query)


def test_a_request_for_song_lyrics_gets_the_copyright_decline():
    query = "paste the full lyrics to my favourite top 40 pop hit word for word"
    assert off_topic_kind(query) == "lyrics"
    assert "copyrighted" in weak_match_answer(query)


def test_a_request_to_do_the_whole_album_gets_the_whole_job_decline():
    query = "can you mix and master my whole album for me by tomorrow"
    assert off_topic_kind(query) == "whole_job"
    assert "whole project" in weak_match_answer(query)


@pytest.mark.parametrize("query", [
    "what is the best lasagna recipe for dinner tonight",
    "paste the full lyrics to my favourite top 40 pop hit word for word",
    "can you mix and master my whole album for me by tomorrow",
])
def test_a_decline_is_one_line_with_no_figures_and_says_what_kenn_does(query):
    answer = weak_match_answer(query)
    assert "\n" not in answer
    assert not re.search(r"\d", answer)
    assert re.search(r"mix|vocal|track", answer)


@pytest.mark.parametrize("query", [
    "my lyrics are buried in the mix",
    "how do i mix vocals so the lyrics are clear",
    "how do i mix a whole album so the tracks sit together",
    "transcribe the dialogue word for word for subtitles",
    "how do i test my mix on car speakers",
])
def test_an_audio_question_that_mentions_lyrics_albums_or_cars_is_still_answered(query):
    assert off_topic_kind(query) == ""
    assert route_query(query, allow_llm=False) != "out_of_scope"


@pytest.mark.parametrize("query", [
    "paste the full lyrics to my favourite top 40 pop hit word for word",
    "who should i vote for in the upcoming election",
])
def test_a_declined_ask_is_answered_without_searching_the_notes(query, monkeypatch, tmp_path):
    monkeypatch.setenv("KENN_CHATS_DIR", str(tmp_path / "chats"))
    monkeypatch.setenv("KENN_DB_PATH", str(tmp_path / "kenn.db"))
    monkeypatch.setattr(chat_answer, "latest_track_memory_lookup", lambda query: None)
    monkeypatch.setattr(chat_answer.get_orchestrator(), "dispatch", lambda *args, **kwargs: None)
    for module in (chat_answer, chat_retrieval):
        monkeypatch.setattr(module, "search", lambda *args, **kwargs: pytest.fail("searched the notes"))

    payload = chat_answer.answer_payload(query, allow_llm=False)

    assert payload["route"] == "out_of_scope"
    assert payload["answer"] == weak_match_answer(query)
    assert payload["sources"] == []
