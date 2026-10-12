"""A tag naming the wrong excerpt is repaired, not paid for with the whole answer (11 Oct 2026: 2 of 72 held-out).

The tag moves to an excerpt that holds the figure, or goes when none does. No figure changes, so the measurement
check still decides every number that ships.
"""

from __future__ import annotations

import pytest

from kenn.core import chat_answer
from kenn.core.chat_grounding import (
    end_on_a_whole_sentence,
    generated_answer_validation,
    repair_misattributed_citations,
    salvage_unsupported_figures,
)
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


def _check_with_question_figure(answer: str) -> dict:
    # The producer's 300 ms is in no note, so a tag on it can only be dropped, never moved.
    return generated_answer_validation(
        SIDECHAIN_QUERY,
        RESULTS,
        answer,
        route="production",
        confidence="high",
        answer_mode="mix_diagnosis",
        question="My release is at 300 ms. " + SIDECHAIN_QUERY,
    )


@pytest.mark.parametrize(
    ("written", "shipped"),
    [
        # Each of these left a stray mark before 11 Oct: "300 ms ().", "300 ms\u00a0." and "-Keep".
        ("Keep the release at 300 ms ([#1]).", "Keep the release at 300 ms."),
        ("Keep the release at 300 ms\u00a0[#1].", "Keep the release at 300 ms."),
        ("Keep the release at 300 ms [#1] for now.", "Keep the release at 300 ms for now."),
        ("At 300 ms [#1]\nkeep it.", "At 300 ms\nkeep it."),
        # A space after a tag that ends its line stayed until 12 Oct.
        ("At 300 ms [#1] \nkeep it.", "At 300 ms\nkeep it."),
    ],
)
def test_a_dropped_tag_leaves_no_stray_space_or_brackets(written, shipped):
    assert _repaired(_answer(written), _check_with_question_figure) == _answer(shipped)


@pytest.mark.parametrize("line", ["[#1] Keep the release at 300 ms.", "- [#1] Keep the release at 300 ms."])
def test_a_dropped_tag_at_the_start_of_a_line_leaves_the_line_as_written(line):
    # Before 11 Oct a tag opening a bare line shipped it with a leading space.
    shipped = line.replace("[#1] ", "")

    assert f"\n{shipped}" in _repaired(_answer(f"Here is the plan.\n{line}"), _check_with_question_figure)


def test_a_junk_tag_split_by_the_range_rewrite_stops_the_repair():
    # 11 Oct review: "[#5-150ms]" is a tag as written but the range rewrite splits it, so the gate counted one tag
    # fewer and the repair edited the junk tag in place of the wrong one.
    answer = _answer("Duck the send to 12% [#5-150ms], with the release at 150 ms [#2].")
    assert validate(answer)["claim_citations"]["fabricated_attributions"]

    assert _repaired(answer) == ""


@pytest.mark.parametrize(
    ("written", "shipped"),
    [
        # Until 12 Oct each of these lost the space between the figure and the next word ("300 msfor now."). A
        # figure glued to a word is one the measurement check cannot see.
        ("Keep the release at 300 ms[#1] for now.", "Keep the release at 300 ms for now."),
        ("Keep the release at 300 ms([#1]) for now.", "Keep the release at 300 ms for now."),
        ("Keep the release at 300 ms[#1]for now.", "Keep the release at 300 ms for now."),
        ("Keep the release at 300 ms [#1]for now.", "Keep the release at 300 ms for now."),
        ("Keep the release at 300 ms\t[#1]for now.", "Keep the release at 300 ms\tfor now."),
    ],
)
def test_a_dropped_tag_never_glues_its_figure_to_the_next_word(written, shipped):
    assert _repaired(_answer(written), _check_with_question_figure) == _answer(shipped)


def test_a_repair_that_would_change_a_figure_repairs_nothing():
    # "300[#1] ms" holds no figure as written. Without its tag it reads "300 ms", a figure the gate never judged.
    answer = _answer("Keep the release at 300[#1] ms.")

    assert repair_misattributed_citations(answer, [{"citation_index": 0, "attributed_ordinals": []}]) == ""


def _make_answer_returning(monkeypatch, text: str, chunks=CHUNKS, query=QUERY, **kwargs) -> tuple[str, bool, list]:
    monkeypatch.setattr(chat_answer, "load_chunks", lambda: list(chunks))
    monkeypatch.setattr(chat_answer, "search", lambda *a, **k: list(chunks))
    monkeypatch.setattr(chat_answer, "should_use_llm_rewrite", lambda *a, **k: True)
    monkeypatch.setattr(chat_answer, "llm_enhance_answer", lambda *a, **k: text)
    monkeypatch.setattr("kenn.llm.linter.lint_response", lambda answer, mode: answer)
    logged = []
    monkeypatch.setattr(
        chat_answer, "_log_generation_outcome", lambda accepted, validation, seconds: logged.append((accepted, validation))
    )
    answer, enhanced = chat_answer.make_answer(query, list(chunks), route="production", **kwargs)
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


def test_make_answer_does_not_repair_an_answer_refused_for_something_else(monkeypatch):
    # 11 Oct review: dropping a tag edits the prose other checks read ("4:1 [#2]. Then" becomes "4:1. Then", a
    # numbered step to the quality check), so a quality or overlap refusal could vanish with the tag. This gate
    # refuses for as long as the wrong tag is there, which is how such a fault looks from make_answer.
    real = chat_answer.generated_answer_validation

    def refuses_while_the_tag_stands(*args, **kwargs):
        validation = real(*args, **kwargs)
        if WRONG_TAG in args[2]:
            validation = {**validation, "accepted": False, "warnings": [*validation["warnings"], "fewer than two actionable steps"]}
        return validation

    monkeypatch.setattr(chat_answer, "generated_answer_validation", refuses_while_the_tag_stands)
    answer, enhanced, logged = _make_answer_returning(
        monkeypatch, ACCEPTED_ANSWER.replace("the depth to 6 dB so", WRONG_TAG)
    )

    assert enhanced is False
    assert logged[-1][0] is False


def test_make_answer_does_not_credit_a_repair_the_figure_cut_threw_away(monkeypatch):
    # 11 Oct review: the wrong tag shared a step with the invented 900 ms, the cut took the step, and the log still
    # said "citations repaired".
    answer, enhanced, logged = _make_answer_returning(
        monkeypatch, INVENTED_IN_A_STEP.replace("out to 900 ms if", "out to 900 ms from 5 ms [#2] if")
    )

    assert enhanced is True
    assert "900" not in answer and "5 ms" not in answer
    assert logged[-1][1]["salvaged"] == ["900ms"]
    assert logged[-1][1]["repaired_citations"] == []


def test_make_answer_never_ships_an_invented_figure_once_its_tag_is_dropped(monkeypatch):
    # 11 Oct review: dropping the tag from "900 ms[#2] so" took the only space, the gate could not see "900 msso" as
    # a figure, and the step shipped with its invented 900 ms.
    answer, _enhanced, _logged = _make_answer_returning(
        monkeypatch,
        INVENTED_IN_A_STEP.replace(
            "out to 900 ms if the kick feels choked.", "out to 900 ms[#2] so the kick breathes. Start from 900 ms."
        ),
    )

    assert "900" not in answer


# The text as written passes everything but the tag, because the dangling "2. Set the" counts as a step. The cut
# ending loses that step, and dropping the tag turns "4:1. Then" into one.
CUT_LOSES_A_STEP = (
    "Short answer: Pull the bass compressor release in from 300 ms so the bass recovers before the kick.\n\n"
    "Check: Compare the bass in context.\n\n"
    "Try this: 1. Key the bass bus compressor from the kick at 300 ms with a ratio of 4:1 [#2]. "
    "Then listen to the bass against the kick. 2. Set the"
)


def test_make_answer_does_not_repair_a_cut_ending_refused_for_quality(monkeypatch):
    # 11 Oct review: the repair ran on the warnings for the text as written, and then shipped the cut ending, which
    # also failed on quality, with "4:1. Then" standing in for the step the cut took.
    whole = end_on_a_whole_sentence(CUT_LOSES_A_STEP)
    assert _check_with_question_figure(CUT_LOSES_A_STEP)["warnings"] == [MISATTRIBUTED]
    assert "generated answer is below the quality threshold" in _check_with_question_figure(whole)["warnings"]
    assert _check_with_question_figure(whole.replace(" [#2]", ""))["accepted"] is True

    answer, enhanced, _logged = _make_answer_returning(
        monkeypatch,
        CUT_LOSES_A_STEP,
        chunks=RESULTS,
        query=SIDECHAIN_QUERY,
        answer_mode="mix_diagnosis",
        question="My release is at 300 ms. " + SIDECHAIN_QUERY,
    )

    assert enhanced is True
    assert answer == CUT_LOSES_A_STEP.replace(" [#2]", "")


def test_make_answer_does_not_repair_quality_lost_when_an_invented_step_is_cut(monkeypatch):
    # 12 Oct recheck: the original passed quality, but cutting its invented second step left one real step.
    # Dropping the tag then made "4:1. Then" count as the missing step unless the cut twin was checked too.
    written = CUT_LOSES_A_STEP.replace("2. Set the", "2. Set the attack to 900 ms.")
    validation = _check_with_question_figure(written)
    assert set(validation["warnings"]) == {MISATTRIBUTED, "generated answer introduced unsupported measurements"}
    cut = salvage_unsupported_figures(written, validation["unsupported_measurements"])
    assert "generated answer is below the quality threshold" in _check_with_question_figure(cut)["warnings"]
    assert _check_with_question_figure(cut.replace(" [#2]", ""))["accepted"] is True

    _answer, enhanced, logged = _make_answer_returning(
        monkeypatch, written, chunks=RESULTS, query=SIDECHAIN_QUERY, answer_mode="mix_diagnosis",
        question="My release is at 300 ms. " + SIDECHAIN_QUERY,
    )

    assert enhanced is False
    assert logged[-1][0] is False
