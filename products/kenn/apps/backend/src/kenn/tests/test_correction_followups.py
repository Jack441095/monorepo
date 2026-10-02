import pytest

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
