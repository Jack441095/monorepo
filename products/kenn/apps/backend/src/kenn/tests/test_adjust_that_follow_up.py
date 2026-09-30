"""A producer who says "adjust that" is answering their own question, so KENN has to quote what it would adjust.

B6, 2026-09-30. "adjust that" carries no amount, so it cannot become a command; it needs to be asked back. Before
this it fell through the generic anaphora branch -- "that" was replaced with the last track, "adjust Hi-Hats" is not a
command -- and the reply was the catch-all "I didn't catch a change to make there", which is true and useless.
"""

from __future__ import annotations

import itertools

import pytest

from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command
from kenn.core.fake_live import FakeLiveBackend

_counter = itertools.count()


def _ask(request_text: str, session_id: str | None = None) -> dict:
    """A fresh session unless one is given, because these scenarios deliberately build history."""
    return handle_command(request_text, session_id=session_id or f"adjust-{next(_counter)}",
                          service=LiveActionService(FakeLiveBackend()), allow_llm=False)


@pytest.mark.parametrize("phrase", ["adjust that", "adjust it", "adjust this", "adjust that one",
                                    "please adjust that", "adjust that a bit"])
def test_adjust_asks_by_how_much_and_quotes_the_previous_request(phrase: str) -> None:
    session = f"adjust-variant-{phrase}"
    proposal = _ask("turn the hats down 3 dB", session)
    assert proposal["status"] == "confirmation_required" and proposal["changed"] is False
    result = _ask(phrase, session)
    assert result["status"] == "clarification_required"
    assert 'turn the hats down 3 dB' in result["answer"], result["answer"]
    assert "By how much" in result["answer"]


def test_adjust_quotes_a_two_step_proposal_so_the_producer_can_see_what_it_would_change() -> None:
    session = "adjust-two-step"
    _ask("turn the hats down 3 dB and the kick up 2 dB", session)
    answer = _ask("adjust that", session)["answer"]
    assert "turn the hats down 3 dB and the kick up 2 dB" in answer, answer


def test_adjust_writes_nothing() -> None:
    session = "adjust-no-write"
    _ask("turn the hats down 3 dB", session)
    result = _ask("adjust that", session)
    assert result["changed"] is False


def test_adjust_with_nothing_to_adjust_says_so_rather_than_inventing_one() -> None:
    answer = _ask("adjust that")["answer"]
    assert "didn't catch a change" in answer, "no history means no previous command to quote"


def test_asking_the_adjustment_amount_is_a_normal_follow_up() -> None:
    """The question has to be answerable the way every other KENN question is."""
    session = "adjust-answered"
    _ask("turn the hats down 3 dB", session)
    _ask("adjust that", session)
    result = _ask("make it 2 dB instead", session)
    assert result["status"] in {"confirmation_required", "clarification_required"}
    assert result["changed"] is False