"""The 128-token cap stops most model answers mid-word (4 Oct 2026: 25 of 27 accepted answers did)."""

from __future__ import annotations

from kenn.core import chat_answer
from kenn.core.chat_grounding import end_on_a_whole_sentence
from kenn.tests.test_streamed_generation_prefix_guard import ACCEPTED_ANSWER, CHUNKS, QUERY

SOURCES = "\n\nSources:\n- Bass Compression (bass-compression.md)"
BODY = (
    "Short answer: Key the bass compressor from the kick and let the release recover before the next hit.\n"
    "Try this:\n1. Put a compressor on the bass bus and send the kick to its sidechain input.\n"
    "2. Set the release so the bass recovers before the next kick lands.\n"
    "Check: Solo the bass and the kick together and listen for the pumping settling in time.\n"
)


def test_an_answer_that_already_ends_cleanly_is_left_alone():
    assert end_on_a_whole_sentence(BODY.rstrip() + SOURCES) == BODY.rstrip() + SOURCES


def test_the_fixture_answer_is_left_alone():
    assert end_on_a_whole_sentence(ACCEPTED_ANSWER) == ACCEPTED_ANSWER


def test_a_last_line_with_no_full_stop_goes_and_the_sources_stay():
    cut = BODY + "Why it matters: Sidechain pumping relies on the release finishing before the next" + SOURCES
    assert end_on_a_whole_sentence(cut) == BODY.rstrip() + SOURCES


def test_a_last_line_keeps_the_sentences_that_were_finished():
    cut = BODY + "Why it matters: A short release pumps. A long one smears the next and is" + SOURCES
    assert end_on_a_whole_sentence(cut).endswith("A short release pumps." + SOURCES)


def test_a_decimal_is_not_taken_for_a_full_stop():
    cut = BODY + "Why it matters: Try a ratio of 4.5" + SOURCES
    assert end_on_a_whole_sentence(cut) == BODY.rstrip() + SOURCES


def test_an_answer_with_no_sources_list_is_trimmed_too():
    assert end_on_a_whole_sentence(BODY + "Why it matters: Sidechain pumping relies on") == BODY.rstrip()


def test_a_short_answer_is_not_cut_down_to_nothing():
    cut = "Short answer: Key it from the kick. Then the release has to recover before"
    assert end_on_a_whole_sentence(cut) == cut


def test_make_answer_shows_the_whole_sentence_ending(monkeypatch):
    monkeypatch.setattr(chat_answer, "load_chunks", lambda: list(CHUNKS))
    monkeypatch.setattr(chat_answer, "search", lambda *a, **k: list(CHUNKS))
    monkeypatch.setattr(chat_answer, "should_use_llm_rewrite", lambda *a, **k: True)
    cut = ACCEPTED_ANSWER.replace(
        "\n\nSources:", "\nWhy it matters: Releasing too slowly keeps the bass ducked after the\n\nSources:"
    )
    monkeypatch.setattr(chat_answer, "llm_enhance_answer", lambda *a, **k: cut)
    monkeypatch.setattr("kenn.llm.linter.lint_response", lambda answer, mode: answer)
    monkeypatch.setattr(chat_answer, "_log_generation_outcome", lambda *a, **k: None)

    answer, enhanced = chat_answer.make_answer(QUERY, list(CHUNKS), route="production")

    assert enhanced is True
    assert "Why it matters" not in answer
