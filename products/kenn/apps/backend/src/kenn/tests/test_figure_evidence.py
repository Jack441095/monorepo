"""The gate accepts a figure the producer typed or a shown note states, and still refuses one from anywhere else.

8 Oct 2026 bench (kenn-evaluation-data/2026-10-08-refused-figures): 116 figures refused over 12 runs. 20 were in the
producer's own question and 23 in a shown note past its 400-character excerpt.
"""

from __future__ import annotations

import pytest

from kenn.core import chat_grounding
from kenn.core.chat_grounding import (
    _evidence_chunks,
    _measurements,
    evidence_measurements,
    generated_answer_validation,
)

# 552 characters with no figure in them. The model is shown the first 400 (_CONTEXT_CHUNK_CHARS in llm_rewrite), so
# the sentence after this is in the note but never in the excerpt.
LEAD = "Streaming services turn loud masters down, so pushing level past their target buys nothing. " * 6

SHOWN = {
    "id": "loud-short",
    "kind": "note",
    "title": "Loudness For Streaming",
    "source": "loudness-for-streaming.md",
    "page": 0,
    "section": "Short answer",
    "text": LEAD + "Leave the true peak at -1 dBTP so the lossy encode does not clip.",
}
SIBLING = {
    "id": "loud-check",
    "kind": "note",
    "title": "Loudness For Streaming",
    "source": "loudness-for-streaming.md",
    "page": 0,
    "section": "Check",
    "text": "Measure the integrated level over the whole song; most services normalise to -14 LUFS.",
}
OTHER_NOTE = {
    "id": "vocal-comp",
    "kind": "note",
    "title": "Vocal Compression",
    "source": "vocal-compression.md",
    "page": 0,
    "section": "Try this",
    "text": "Start with 3 dB of gain reduction on the vocal and listen for the breaths.",
}
MANUAL_PAGE = {
    "id": "manual-212",
    "kind": "manual",
    "title": "Live 12 Reference Manual",
    "source": "live12-manual.pdf",
    "page": "212",
    "section": "",
    "text": "EQ Eight has eight bands per channel, each with its own filter type.",
}
NEXT_MANUAL_PAGE = {**MANUAL_PAGE, "id": "manual-213", "page": "213", "text": "The low cut defaults to 30 Hz."}

QUERY = "How loud should my master be for Spotify?"

# model_evidence() drops anything scored under 4.0 as too weak to show, so a fixture scored 1.0 is never evidence.
SCORE = 50.0


@pytest.fixture
def index(monkeypatch):
    """The whole-index copy the gate reads a shown note's other sections from."""
    def use(*chunks: dict) -> None:
        monkeypatch.setattr(chat_grounding, "load_chunks", lambda: list(chunks))

    use()
    return use


def _refused(answer: str, results: list[dict], query: str = QUERY, question: str = "") -> list[str]:
    """`query` is the history-expanded search string the gate is called with, `question` what the producer typed."""
    return generated_answer_validation(
        query, [(SCORE, chunk) for chunk in results], answer,
        route="production", confidence="high", answer_mode="quick_fix", question=question,
    )["unsupported_measurements"]


def test_the_fixture_note_puts_its_figure_past_the_excerpt_the_model_sees():
    # Without this, the past-the-excerpt test below would pass on the old gate too and prove nothing.
    (_score, _chunk, body), = _evidence_chunks([(SCORE, SHOWN)])
    assert "-1dbtp" not in _measurements(body)


def test_a_figure_past_the_excerpt_of_a_shown_note_is_accepted(index):
    assert _refused("Keep the true peak at -1 dBTP before you export.", [SHOWN]) == []


def test_a_figure_from_another_section_of_a_shown_note_is_accepted(index):
    index(SHOWN, SIBLING, OTHER_NOTE)
    assert _refused("Aim for -14 LUFS integrated.", [SHOWN]) == []


def test_decimal_equivalent_figure_matches_integer_source(index):
    # SIBLING has -14 LUFS; an answer writing -14.0 LUFS is equivalent and accepted.
    index(SHOWN, SIBLING)
    assert _refused("Aim for -14.0 LUFS integrated.", [SHOWN]) == []


def test_integer_within_recommended_range_is_accepted():
    # Note has 3–6 dB; an answer recommending 4 dB or 5 dB is within the note's guidance.
    range_chunk = {
        "id": "bv-levels", "kind": "note", "title": "Background Vocals", "source": "bvs.md",
        "page": 0, "section": "Try this", "text": "Set BV levels 3–6 dB below the lead vocal.",
    }
    assert _refused("Set the backing vocals 5 dB below the lead.", [range_chunk]) == []
    assert _refused("Set the backing vocals 4 dB below the lead.", [range_chunk]) == []
    # 7 dB is outside the 3–6 dB range and must be refused.
    assert _refused("Set the backing vocals 7 dB below the lead.", [range_chunk]) == ["7db"]


def test_colloquial_question_figures_are_accepted():
    # User types 'boosted around 5k', model responds with '5 kHz'.
    q = "why do my vocals sound harsh after I boosted around 5k?"
    assert _refused("Harshness at 5 kHz is common with high boosts.", [OTHER_NOTE], q, q) == []

    # User types '+0.8 true peak', model responds with '0.8 dBTP'.
    q_tp = "my limiter says +0.8 true peak but 0.0 peak help"
    assert _refused("True peak at 0.8 dBTP indicates overshoot.", [OTHER_NOTE], q_tp, q_tp) == []


def test_a_figure_only_an_unshown_note_states_is_still_refused(index):
    # The 2 Oct "wide" bug: a 3 dB waved through on a chunk the model never saw. Widening to the shown note's other
    # sections must not reopen that.
    index(SHOWN, SIBLING, OTHER_NOTE)
    assert _refused("Take 3 dB off the master bus first.", [SHOWN]) == ["3db"]


def test_a_figure_the_producer_typed_is_not_one_the_model_invented(index):
    # eq-kick-bass-phase, 8 Oct: all 8 answers that said the producer's "60 Hz" back were refused.
    question = "Why do my kick and bass cancel around 60 Hz?"
    answer = "The cancel around {} is the two waves out of phase."
    assert _refused(answer.format("60 Hz"), [OTHER_NOTE], question, question) == []
    assert _refused(answer.format("80 Hz"), [OTHER_NOTE], question, question) == ["80hz"]


def test_a_figure_from_an_earlier_turn_is_not_accepted_on_the_follow_ups_say_so(index):
    # On a follow-up the gate's query is search_query_with_history(), which carries the earlier turn's words. Read
    # as "the producer's question", it let the 300 Hz from the last turn through on a turn that never mentioned it
    # (read-only review of this branch, 10 Oct 2026).
    expanded = "cut 300 Hz on the bass by 4 dB? and the guitars?"
    assert _refused("Cut 300 Hz on the guitars too.", [OTHER_NOTE], expanded, "and the guitars?") == ["300hz"]


def test_without_the_producers_question_no_figure_passes_on_the_query_alone(index):
    # A caller that does not pass `question` gets the stricter gate, never the history-expanded one.
    question = "Why do my kick and bass cancel around 60 Hz?"
    assert _refused("The cancel around 60 Hz is the two waves out of phase.", [OTHER_NOTE], question) == ["60hz"]


def test_a_shown_manual_page_does_not_open_the_rest_of_the_manual(index):
    # Every manual chunk shares one source, so widening to "the whole manual" would accept nearly any Hz.
    index(MANUAL_PAGE, NEXT_MANUAL_PAGE)
    assert _refused("Set the low cut to 30 Hz.", [MANUAL_PAGE]) == ["30hz"]


def test_the_stream_guard_allows_the_figures_the_final_gate_allows(index):
    # The guard stops a stream for good, so a figure it refuses and the final gate would accept costs the answer.
    index(SHOWN, SIBLING, OTHER_NOTE)
    allowed = evidence_measurements([(SCORE, SHOWN)], question="Is 60 Hz too low for the sub?")
    assert {"60hz", "-1dbtp", "-14lufs"} <= allowed
    assert "3db" not in allowed


def test_a_follow_up_reaches_make_answer_as_typed_beside_the_expanded_search_string(tmp_path, monkeypatch):
    # make_answer() writes with the history-expanded string retrieval ran on, but the gate inside it takes figures from
    # `question`. Wired to the expanded string, the 300 Hz from the turn before rides in on "and the guitars?".
    from kenn.core import chat_answer, chat_retrieval, route_log, session_memory
    from kenn.tests.test_streamed_generation_prefix_guard import CHUNKS

    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "memory.db")
    monkeypatch.setattr(route_log, "record", lambda *a, **k: None)
    monkeypatch.setattr(chat_answer, "_critique_and_save_trace", lambda **kwargs: None)
    terms = {"total_docs": 0, "avg_len": 1.0, "lengths": [], "idf": {}, "postings": {}}
    for module in (chat_retrieval, chat_answer):
        monkeypatch.setattr(module, "load_chunks", lambda: [c for _, c in CHUNKS])
        monkeypatch.setattr(module, "load_terms", lambda: terms)
        monkeypatch.setattr(module, "search", lambda *args, **kwargs: list(CHUNKS))
    called: dict = {}

    def make_answer(query, *args, **kwargs):
        called.update(query=query, question=kwargs.get("question"))
        return "Short answer: a model answer.", True

    monkeypatch.setattr(chat_answer, "make_answer", make_answer)
    history = [
        {"role": "user", "content": "Should I cut 300 Hz on the bass by 4 dB?"},
        {"role": "assistant", "content": "Try a narrow cut there and listen in the mix."},
    ]
    chat_answer.answer_payload("and the guitars?", history=history, session_id="follow-up", record_session=False)

    assert "300 Hz" in called["query"], "the follow-up has to be history-expanded or this proves nothing"
    assert called["question"] == "and the guitars?"


def test_make_answer_inner_check_takes_figures_from_typed_question_not_expanded_query(monkeypatch):
    """The gate inside make_answer() takes figures from the turn as typed, not the history-expanded query.

    The test above stubs make_answer() to verify what answer_payload() passes it, but that cannot catch a
    mutation inside make_answer() from question=question to question=query. This exercises the real make_answer()
    pipeline, confirming that a figure from the earlier turn is accepted on that turn and refused on a follow-up.
    """
    from kenn.core import chat_answer, chat_grounding
    from kenn.tests.test_streamed_generation_prefix_guard import ACCEPTED_ANSWER, CHUNKS

    # 200 ms is absent from CHUNKS, so only the question's say-so can justify it to the grounding gate.
    ans_200 = ACCEPTED_ANSWER.replace("150 ms", "200 ms")
    chunks = [chunk for _score, chunk in CHUNKS]

    monkeypatch.setattr(chat_answer, "load_chunks", lambda: list(chunks))
    monkeypatch.setattr(chat_grounding, "load_chunks", lambda: list(chunks))
    monkeypatch.setattr(chat_answer, "should_use_llm_rewrite", lambda *args, **kwargs: True)
    monkeypatch.setattr(chat_answer, "llm_enhance_answer", lambda *args, **kwargs: ans_200)
    monkeypatch.setattr("kenn.llm.linter.lint_response", lambda text, mode: text)
    monkeypatch.setattr(chat_answer, "_log_generation_outcome", lambda *args, **kwargs: None)

    earlier = "Should I set the compressor release to 200 ms?"
    results = list(CHUNKS)

    # When query and question are both the earlier turn, the producer typed 200 ms and the answer keeps it.
    ans_kept, used_kept = chat_answer.make_answer(earlier, results, question=earlier, route="production")
    assert used_kept is True
    assert "release to 200 ms" in ans_kept.lower()

    # On a follow-up, the search query is expanded with history and carries 200 ms, but the typed question is
    # "and on the drums?". make_answer()'s inner _check must refuse "release to 200 ms" because the producer
    # did not type it this turn.
    expanded = earlier + " and on the drums?"
    ans_refused, _ = chat_answer.make_answer(
        expanded, results, question="and on the drums?", route="production"
    )
    assert "200 ms" not in ans_refused
