"""Two changes in one sentence must not become a question about one of them.

B6, measured 2026-09-30. "make the hats quieter and the kick punchier" resolved to the Kick, asked "By how much?" and
never mentioned the Hi-Hats again -- so the producer's first request was silently dropped and the reply read as though
they had only asked one thing. Same shape as round 9's "mute the Kick, mute the hats" proposing a single mute.
"""

from __future__ import annotations

import itertools

import pytest

from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command
from kenn.core.fake_live import FakeLiveBackend


_counter = itertools.count()


def _ask(request_text: str) -> dict:
    """A fresh session per call, deliberately.

    Session context is load-bearing here: ask the same sentence twice in one session and the second answer comes from
    clarify_contextual_direction ("relative louder/softer moves are not yet qualified") rather than from the
    missing-value question, because the first exchange established what was being discussed. That is intended
    behaviour, and it is why these scenarios must not share a session id -- with one shared id, the second test
    silently inherited the first one's context and the fix looked broken.
    """
    return handle_command(request_text, session_id=f"b6-{next(_counter)}",
                          service=LiveActionService(FakeLiveBackend()), allow_llm=False)


def test_a_two_change_request_asks_about_both_parts_not_just_one() -> None:
    result = _ask("make the hats quieter and the kick punchier")
    assert result["status"] == "clarification_required" and result["changed"] is False
    answer = result["answer"]
    assert "By how much?" in answer
    assert "the hats quieter" in answer, f"the unhandled part was dropped: {answer}"


def test_the_named_part_is_the_one_the_question_is_not_about() -> None:
    answer = _ask("make the hats quieter and the kick punchier")["answer"]
    assert "turn Kick down 2 dB" in answer, "KENN did resolve the Kick, so it should still ask about it"
    assert "make the hats quieter" in answer


def test_a_single_change_request_is_untouched() -> None:
    answer = _ask("make the hats quieter")["answer"]
    assert "By how much?" in answer and "turn Hi-Hats down 2 dB" in answer
    assert "didn't catch" not in answer


def test_a_two_change_request_that_both_parse_still_makes_one_plan() -> None:
    """The fix must not disturb the case that already worked, which is the whole of what B6 already had."""
    result = _ask("turn the hats down 3 dB and the kick up 2 dB")
    assert result["status"] == "confirmation_required"
    assert "2 changes" in result["answer"] and result["changed"] is False


@pytest.mark.parametrize("request_text, expected", [
    ("make the hats quieter and the kick punchier", "make the hats quieter"),
    ("make the kick punchier and the hats quieter", "the hats quieter"),
])
def test_the_dropped_part_is_named_which_side_of_the_and_it_was_on(request_text: str, expected: str) -> None:
    assert expected in _ask(request_text)["answer"]

def test_a_refusal_names_which_change_is_impossible_instead_of_claiming_none_was_caught() -> None:
    """"lower the bass 2 dB and raise the vocal 1 dB": the Bass is fine, the vocal is at +0.00 dB and cannot rise."""
    result = _ask("lower the bass 2 dB and raise the vocal 1 dB")
    assert result["status"] == "clarification_required" and result["changed"] is False
    answer = result["answer"]
    assert "Lead Vocal" in answer and "raise the vocal 1 dB" in answer, answer
    assert "didn't catch a change" not in answer, "the catch-all is wrong here: one change was understood"


def test_the_catch_all_is_unchanged_for_a_request_that_is_not_a_change_at_all() -> None:
    answer = _ask("make it sound like a purple spaceship")["answer"]
    assert "didn't catch a change to make there" in answer
    assert "Lead Vocal" not in answer


def test_a_two_change_request_that_both_work_is_untouched_by_the_new_refusal() -> None:
    result = _ask("turn the hats down 3 dB and the kick up 2 dB")
    assert result["status"] == "confirmation_required" and "2 changes" in result["answer"]
