"""A tag naming the wrong excerpt is repaired, not paid for with the whole answer (11 Oct 2026: 2 of 72 held-out).

The tag moves to an excerpt that holds the figure, or goes when none does. No figure changes, so the measurement
check still decides every number that ships.
"""

from __future__ import annotations

from kenn.core import chat_answer
from kenn.core.chat_grounding import generated_answer_validation, repair_misattributed_citations
from kenn.tests.test_claim_citation_grounding import QUERY as SIDECHAIN_QUERY
from kenn.tests.test_claim_citation_grounding import RESULTS, _answer, validate
from kenn.tests.test_salvage_unsupported_measurements import INVENTED_IN_A_STEP
from kenn.tests.test_streamed_generation_prefix_guard import ACCEPTED_ANSWER, CHUNKS, QUERY

MISATTRIBUTED = "generated answer attributes a measurement to an excerpt that does not contain it"


def _repaired(answer: str, check=validate) -> str:
    return repair_misattributed_citations(answer, check(answer)["claim_citations"]["fabricated_attributions"])


def test_a_tag_on_the_wrong_excerpt_moves_to_the_one_that_holds_the_figure():
    # Excerpt 1 is the sidechain note with the 150 ms, excerpt 2 the cleanup chain with the 12% send.
    answer = _answer("Release at 150 ms [#1], and duck the send to 12% [#1].")
    assert MISATTRIBUTED in validate(answer)["warnings"]

    repaired = _repaired(answer)

    assert "150 ms [#1]" in repaired and "12% [#2]" in repaired
    check = validate(repaired)
    assert check["accepted"] is True
    assert check["claim_citations"]["citation_agreed"] == 2


def test_a_tag_on_a_figure_from_the_question_goes_and_the_figure_stays():
    # No note holds 300 ms. The producer said it, so the aggregate check accepts it, and there is no excerpt the
    # tag could rightly name.
    def check(answer: str) -> dict:
        return generated_answer_validation(
            SIDECHAIN_QUERY,
            RESULTS,
            answer,
            route="production",
            confidence="high",
            answer_mode="mix_diagnosis",
            question="My release is at 300 ms. " + SIDECHAIN_QUERY,
        )

    answer = _answer("Pull the release in from 300 ms [#1] to 150 ms [#1].")
    assert check(answer)["warnings"] == [MISATTRIBUTED]

    repaired = _repaired(answer, check)

    assert "from 300 ms to 150 ms [#1]." in repaired
    assert check(repaired)["accepted"] is True


def test_a_figure_no_note_holds_is_still_refused_once_its_tag_is_gone():
    answer = _answer("Set the release to 900 ms [#1].")

    repaired = _repaired(answer)

    assert "900 ms." in repaired and "[#" not in repaired
    check = validate(repaired)
    assert check["accepted"] is False
    assert check["unsupported_measurements"] == ["900ms"]


def test_an_answer_whose_tags_are_all_right_has_nothing_to_repair():
    assert _repaired(_answer("Release at 150 ms [#1], and duck the send to 12% [#2].")) == ""


def _make_answer_returning(monkeypatch, text: str) -> tuple[str, bool, list]:
    monkeypatch.setattr(chat_answer, "load_chunks", lambda: list(CHUNKS))
    monkeypatch.setattr(chat_answer, "search", lambda *a, **k: list(CHUNKS))
    monkeypatch.setattr(chat_answer, "should_use_llm_rewrite", lambda *a, **k: True)
    monkeypatch.setattr(chat_answer, "llm_enhance_answer", lambda *a, **k: text)
    monkeypatch.setattr("kenn.llm.linter.lint_response", lambda answer, mode: answer)
    logged = []
    monkeypatch.setattr(
        chat_answer, "_log_generation_outcome", lambda accepted, validation, seconds: logged.append((accepted, validation))
    )
    answer, enhanced = chat_answer.make_answer(QUERY, list(CHUNKS), route="production")
    return answer, enhanced, logged


# 6 dB is in excerpts 1 and 3 of the sidechain fixture, not in excerpt 2, so the repaired tag goes to the first.
WRONG_TAG = "the depth to 6 dB [#2] so"
RIGHT_TAG = "the depth to 6 dB [#1] so"


def test_make_answer_keeps_an_answer_whose_only_fault_was_a_wrong_tag(monkeypatch):
    answer, enhanced, logged = _make_answer_returning(
        monkeypatch, ACCEPTED_ANSWER.replace("the depth to 6 dB so", WRONG_TAG)
    )

    assert enhanced is True
    assert RIGHT_TAG in answer
    assert logged[-1][0] is True and logged[-1][1]["repaired_citations"] == ["6db"]
    assert logged[-1][1]["salvaged"] == []


def test_make_answer_fixes_a_wrong_tag_and_an_invented_figure_in_one_retry(monkeypatch):
    # Either fix alone leaves the other fault for the gate to reject, so both have to land before it judges again.
    answer, enhanced, logged = _make_answer_returning(
        monkeypatch, INVENTED_IN_A_STEP.replace("the depth to 6 dB so", WRONG_TAG)
    )

    assert enhanced is True
    assert "900" not in answer and RIGHT_TAG in answer
    assert logged[-1][1]["salvaged"] == ["900ms"] and logged[-1][1]["repaired_citations"] == ["6db"]
