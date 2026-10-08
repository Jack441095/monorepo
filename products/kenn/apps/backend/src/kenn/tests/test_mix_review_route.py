"""Which messages the orchestrator sends to the mix reviewer, and which are recording questions for the notes."""

from __future__ import annotations

import pytest

from kenn.orchestrator import KennOrchestrator


@pytest.fixture
def orchestrator():
    return KennOrchestrator()


# 4 Oct 2026 gap-finder q227 matched "phase ... issues" and the user got "Upload your mix" for a mic-placement question.
def test_a_phase_question_about_miking_a_guitar_is_not_a_mix_review(orchestrator) -> None:
    question = "recording acoustic guitar with one mic vs two, phase issues when i pan them hard"
    assert orchestrator.classify(question) is None


@pytest.mark.parametrize("request_text", [
    "my mix has phase issues, can you check it",
    "review my mix",
    "Can you analyse my master for clipping problems?",
    "I think the loudness is off on this song, any problems?",
    "any clipping problems?",
    "phase issues",
])
def test_real_mix_review_requests_keep_the_mix_reviewer(orchestrator, request_text) -> None:
    assert orchestrator.classify(request_text) == "mix_reviewer"
