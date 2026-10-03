"""A question KENN cannot place gets a question back, not a chatty line that ignores it."""

from __future__ import annotations

import pytest

from kenn.core.chat_formatting import BANTER_RESPONSES, weak_match_answer


@pytest.mark.parametrize("question", [
    "whasts your advice on white noise?",
    "advice on white noise?",
    "hwo do i do paralel compresion on drms",
    "any tips for a tambourine part",
    "can you explain how an exciter works",
])
def test_a_question_with_no_known_topic_is_never_answered_with_banter(question):
    # 3 Oct: "whasts your advice on white noise?" got "I'm here! Ask me about mixing...".
    answer = weak_match_answer(question)
    assert answer not in BANTER_RESPONSES
    assert "direction" in answer or "which" in answer.lower()


@pytest.mark.parametrize("remark", ["hmm ok", "nice one", "right then"])
def test_a_short_remark_with_no_question_still_gets_the_friendly_line(remark):
    assert weak_match_answer(remark) in BANTER_RESPONSES
