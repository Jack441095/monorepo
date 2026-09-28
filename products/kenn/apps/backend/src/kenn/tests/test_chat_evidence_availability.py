"""Two ways a chat answer could be built with no evidence behind it, both found in the 28 Sept audit.

Neither is a subtle scoring tweak. One retrieved eight good notes and cited none of them; the other
answered a new question out of the previous question's notes.
"""

from __future__ import annotations

import pytest

from kenn.core.chat_answer import _cached_results_cover_query
from kenn.core.chat_retrieval import (
    asks_for_official_reference,
    display_results,
    results_are_weak,
)


REVERB_NOTE = {
    "kind": "note",
    "title": "Reverb Send Workflow",
    "source": "reverb-send-workflow.md",
    "topics": ["reverb", "routing", "mixing"],
    "tags": ["reverb", "return", "send", "mixing"],
    "text": (
        "Create a return track for the reverb, keep the return 100% wet, high-pass it around "
        "200-400 Hz, and begin with a send around 10-20%."
    ),
    "status": "Approved",
}
STRONG_REVERB_RESULTS = [(38.0, REVERB_NOTE)]


# `display_results` refuses to substitute a practical note for the official manual when a producer
# explicitly asks for the manual, and returns an empty list. `results_are_weak` scored the raw
# retrieval list instead, so the caller carried on and built an answer whose Sources: line was empty.
def test_a_manual_question_with_no_official_manual_retrieved_counts_as_weak() -> None:
    assert asks_for_official_reference("what does the manual say about send effects") is True
    assert display_results("what does the manual say about send effects", STRONG_REVERB_RESULTS, 3) == []

    assert results_are_weak("what does the manual say about send effects", STRONG_REVERB_RESULTS) is True


def test_an_empty_display_set_is_weak_whatever_the_raw_scores_say() -> None:
    # 38.0 is well above MIN_RELEVANT_SCORE, so only the display set can catch this.
    assert results_are_weak("how do I set up a send reverb", STRONG_REVERB_RESULTS) is False


def test_a_healthy_retrieval_is_still_not_weak() -> None:
    for query in (
        "how do I set up a send reverb",
        "why does my reverb sound muddy",
        "how wet should the reverb return be",
    ):
        assert results_are_weak(query, STRONG_REVERB_RESULTS) is False, query


def test_a_query_the_retrieved_notes_do_not_cover_is_still_weak() -> None:
    # Guards against the previous fix turning into a blanket "always strong".
    assert results_are_weak("how high should I high-pass a vocal", STRONG_REVERB_RESULTS) is True


# The per-session cache handed back the previous turn's chunks whenever the new question looked like a
# follow-up. "And what release time should I use?" follows a reverb send question, and send notes
# cannot answer it, so the model was asked to answer question B out of question A's evidence.
def test_a_follow_up_about_a_new_subject_is_not_answered_from_the_cached_notes() -> None:
    assert _cached_results_cover_query("and what release time should I use?", STRONG_REVERB_RESULTS) is False
    assert _cached_results_cover_query("what about de-essing?", STRONG_REVERB_RESULTS) is False
    assert _cached_results_cover_query("do that on the snare too", STRONG_REVERB_RESULTS) is False


def test_a_follow_up_about_the_same_subject_still_uses_the_cached_notes() -> None:
    # The saving has to survive, or every follow-up turn pays for a fresh index scan.
    assert _cached_results_cover_query("how do I set the return 100% wet?", STRONG_REVERB_RESULTS) is True
    assert _cached_results_cover_query("should the send be higher on the reverb?", STRONG_REVERB_RESULTS) is True


def test_a_follow_up_with_no_subject_of_its_own_inherits_the_cached_notes() -> None:
    for query in ("what about that?", "and then?", "is that right?", "tell me more"):
        assert _cached_results_cover_query(query, STRONG_REVERB_RESULTS) is True, query


def test_an_empty_cached_set_is_never_treated_as_covering_the_question() -> None:
    assert _cached_results_cover_query("how do I set up a send reverb", []) is False


@pytest.mark.parametrize(
    "query",
    [
        "check the docs for how to set up a reverb send",
        "what does the official ableton manual say about send effects",
        "what does the manual recommend for de-essing",
    ],
)
def test_every_documentation_flavoured_question_is_caught(query: str) -> None:
    # "docs", "manual" and "reference manual" all trip the official-reference check, so all three had to
    # be covered or the fix would only hold for the wording we happened to test.
    assert asks_for_official_reference(query) is True
    assert results_are_weak(query, STRONG_REVERB_RESULTS) is True
