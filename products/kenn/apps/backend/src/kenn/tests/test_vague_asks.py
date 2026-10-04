"""A vague ask of a few words gets one question back instead of whichever note matched its loosest word."""

import pytest

from kenn.core.chat_routing import (
    clarification_payload,
    history_context_line,
    is_vague_ask,
    route_query,
    search_query_with_history,
)


@pytest.mark.parametrize("query", [
    "make my vocals better",
    "mix sounds bad",
    "my beat feels empty",
    "guitars sound weird",
    "podcast sounds off",
    "make it sound pro",
    "film score boring",
])
def test_a_vague_ask_with_no_device_and_no_problem_is_asked_back(query):
    assert is_vague_ask(query)
    assert route_query(query, allow_llm=False) == "clarify"


@pytest.mark.parametrize("query", [
    "how do i master",
    "how to mix rock",
    "bass feels weak",
    "my mix is quiet",
    "drums don't hit",
    "need bigger drop",
    "make my compressor better",
    "make drums sound better in ableton",
    "make the vocal better with Serum",
    "turn the reverb off",
    "why does my mix sound bad on phone speakers",
])
def test_an_ask_that_names_a_device_or_a_problem_is_not_vague(query):
    assert not is_vague_ask(query)


def test_the_question_back_names_the_thing_the_producer_mentioned():
    answer = clarification_payload("make my vocals better")["answer"]
    assert answer.startswith("What does the vocal sound like")
    assert answer.count("?") == 1


def test_the_question_back_does_not_guess_a_subject_when_none_was_given():
    answer = clarification_payload("make it sound pro")["answer"]
    assert answer.startswith("What does it sound like")


def test_a_second_vague_ask_gets_the_reset_wording_not_the_same_question_again():
    first = clarification_payload("mix sounds bad")["answer"]
    history = [
        {"role": "user", "content": "mix sounds bad"},
        {"role": "assistant", "content": first},
    ]
    second = clarification_payload("everything sounds bad", history)["answer"]
    assert second != first
    assert "reset" in second.lower()


def test_a_follow_up_that_sounds_vague_is_answered_in_the_context_of_the_last_question():
    history = [{"role": "user", "content": "how do i compress rock drums to keep the transient snap"}]
    assert route_query("and the kick bigger?", history, allow_llm=False) != "clarify"


@pytest.mark.parametrize("reply", ["muddy", "harsh", "too quiet on the vocal"])
def test_the_reply_to_our_question_is_searched_with_the_ask_it_answers(reply):
    # 4 Oct 2026 review: "muddy" after "mix sounds bad" was searched alone and the mix was forgotten.
    history = [
        {"role": "user", "content": "mix sounds bad"},
        {"role": "assistant", "content": clarification_payload("mix sounds bad")["answer"]},
    ]
    assert search_query_with_history(reply, history) == f"mix sounds bad {reply}"
    assert "mix sounds bad" in history_context_line(reply, history)


def test_a_short_question_after_an_ordinary_answer_is_not_glued_to_the_last_one():
    history = [
        {"role": "user", "content": "mix sounds bad"},
        {"role": "assistant", "content": "Short answer: start with the low mids."},
    ]
    assert search_query_with_history("harsh", history) == "harsh"
