"""Advice and how-to questions are not symptom reports (3 Oct: every drum/bass question opened with "Let's trace the symptom")."""

from __future__ import annotations

import pytest

from kenn.core.chat_routing import classify_answer_mode, route_query


def _mode(question: str) -> str:
    return classify_answer_mode(question, route_query(question))


@pytest.mark.parametrize(
    "question",
    [
        "whats your advice on drum compression?",
        "how do I compress bass?",
        "any tips for mixing vocals?",
        "advice on mixing low end?",
    ],
)
def test_an_advice_question_is_not_opened_as_a_symptom_trace(question):
    assert _mode(question) != "mix_diagnosis"


@pytest.mark.parametrize(
    "question",
    [
        "educate me on compression",
        "teach me about sidechain compression",
        "tell me about compression",
        "walk me through EQ on a bass",
        "help me understand compression",
        "i want to learn about compression",
        "describe sidechain compression",
    ],
)
def test_a_learn_request_gets_the_reasoning_shape_not_a_symptom_trace(question):
    # 4 Oct: "educate me on compression" came back as "Let's trace the symptom" with a bass-compression template.
    assert _mode(question) == "deep_explanation"


@pytest.mark.parametrize(
    "question",
    [
        "my vocal sounds harsh",
        "the bass is too boomy in the club",
        "why does my kick sound thin?",
        "drums are muddy and I can't hear the snare",
    ],
)
def test_a_symptom_report_still_gets_the_diagnosis_shape(question):
    assert _mode(question) == "mix_diagnosis"


def test_why_questions_about_a_mix_topic_get_the_reasoning_shape():
    assert _mode("why do we compress vocals?") == "deep_explanation"
