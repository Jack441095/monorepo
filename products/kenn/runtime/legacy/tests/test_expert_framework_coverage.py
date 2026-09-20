"""Regression coverage for the minimum expert diagnostic framework catalogue.

These are symptom-shaped prompts, not recipe requests.  Every one must reach
the causal planner and retain the same hypothesis/test/verification boundary.
"""

from __future__ import annotations

import pytest

from kenn.core.diagnostic_framework import plan_for, render
from kenn.core.chat import answer_payload


def test_house_kick_selection_retrieves_selection_guidance_not_layering() -> None:
    """A selection question needs in-context audition criteria, not a recipe
    for adding layers.  This guards the real symptom seen in desktop use."""
    payload = answer_payload("Can you help me choose a kick for house music?", allow_llm=False)
    answer = str(payload.get("answer") or "").lower()
    sources = {str(item.get("source") or "") for item in payload.get("sources") or [] if isinstance(item, dict)}

    assert "house-kick-selection.md" in sources
    assert "candidate" in answer
    assert "bass" in answer
    assert "matched loudness" in answer


def test_deep_house_kick_selection_beats_the_related_bass_framework() -> None:
    payload = answer_payload("I am making deep house and need help choosing a kick.", allow_llm=False)
    sources = [str(item.get("source") or "") for item in payload.get("sources") or [] if isinstance(item, dict)]
    assert sources[0] == "house-kick-selection.md"


@pytest.mark.parametrize(("query", "source", "must_include"), [
    ("How do I choose a compressor for vocals?", "vocal-compressor-selection.md", "clip gain"),
    ("Which sounds should I choose for a deep house bassline?", "deep-house-bass-sound-selection.md", "bass candidates"),
    ("Should my kick be in key with the bass?", "kick-tuning-with-bass.md", "does not have to be tuned exactly"),
])
def test_selection_questions_retrieve_their_own_decision_framework(
    query: str, source: str, must_include: str
) -> None:
    payload = answer_payload(query, allow_llm=False)
    answer = str(payload.get("answer") or "").lower()
    sources = {str(item.get("source") or "") for item in payload.get("sources") or [] if isinstance(item, dict)}

    assert source in sources
    assert must_include in answer


@pytest.mark.parametrize(("query", "source", "must_include"), [
    ("How do I choose a reverb for lead vocals?", "vocal-reverb-delay-selection.md", "intended depth role"),
    ("How do I choose the right delay for a vocal?", "vocal-reverb-delay-selection.md", "musical division"),
    ("How do I arrange a house track so the chorus feels bigger?", "house-section-energy-arrangement.md", "contrast"),
])
def test_space_and_arrangement_decisions_retrieve_specific_frameworks(
    query: str, source: str, must_include: str
) -> None:
    payload = answer_payload(query, allow_llm=False)
    answer = str(payload.get("answer") or "").lower()
    sources = {str(item.get("source") or "") for item in payload.get("sources") or [] if isinstance(item, dict)}

    assert source in sources
    assert must_include in answer


def test_reference_selection_is_not_misrouted_as_a_tonal_diagnosis() -> None:
    payload = answer_payload("How do I choose a song reference for a dark pop mix?", allow_llm=False)
    assert "Diagnosis first:" not in str(payload.get("answer") or "")


def test_reference_selection_retrieves_a_selection_framework() -> None:
    payload = answer_payload("How do I choose a song reference for a dark pop mix?", allow_llm=False)
    answer = str(payload.get("answer") or "").lower()
    sources = {str(item.get("source") or "") for item in payload.get("sources") or [] if isinstance(item, dict)}

    assert "reference-track-selection.md" in sources
    assert "primary reference" in answer


def test_reverb_wash_followup_is_a_fresh_section_specific_diagnosis() -> None:
    payload = answer_payload(
        "The short plate works in the verse but washes out the chorus. What should I change?",
        allow_llm=False,
    )
    answer = str(payload.get("answer") or "")
    assert "Diagnosis first:" in answer
    assert "section-specific send or return automation" in answer
    assert "Verification:" in answer


def test_vocal_too_far_back_is_diagnosed_as_a_vocal_problem() -> None:
    payload = answer_payload("My vocal still feels too far back. What should I test first?", allow_llm=False)
    answer = str(payload.get("answer") or "")
    assert "Diagnosis first:" in answer
    assert "The vocal is not consistently audible" in answer


def test_non_diagnostic_production_answers_adapt_to_explicit_skill_level() -> None:
    beginner = answer_payload(
        "I am a beginner. How do I choose a compressor for vocals?",
        allow_llm=False,
        session_id="skill-adaptation-beginner",
    )["answer"]
    advanced = answer_payload(
        "I am an advanced engineer. How do I choose a compressor for vocals?",
        allow_llm=False,
        session_id="skill-adaptation-advanced",
    )["answer"]

    assert "Plain-language note:" in beginner
    assert "`Clip gain`" in beginner
    assert "Advanced lens:" in advanced
    assert "gain-reduction timing" in advanced


@pytest.mark.parametrize(("query", "source", "must_include"), [
    ("How do I stop vocal feedback in a small live venue?", "live-vocal-feedback-control.md", "gain-before-feedback"),
    ("My kick has clicks after warping it in Ableton. What should I test?", "ableton-warped-kick-clicks.md", "turn warp off"),
])
def test_cross_domain_safety_questions_retrieve_their_specific_workflow(
    query: str, source: str, must_include: str
) -> None:
    payload = answer_payload(query, allow_llm=False)
    answer = str(payload.get("answer") or "").lower()
    sources = [str(item.get("source") or "") for item in payload.get("sources") or [] if isinstance(item, dict)]

    assert sources[0] == source
    assert must_include in answer


def test_uncovered_1176_question_uses_general_vocal_compression_not_deessing(monkeypatch: pytest.MonkeyPatch) -> None:
    # The exact-hardware limitation must remain deterministic; do not let an
    # optional rewrite wait or invent details after the grounded fallback.
    def rewrite_must_not_run(*args: object, **kwargs: object) -> str:
        raise AssertionError("uncovered hardware response attempted an LLM rewrite")

    monkeypatch.setattr("kenn.core.chat_answer.llm_enhance_answer", rewrite_must_not_run)
    payload = answer_payload("How do I use a 1176 on a vocal?", allow_llm=True, session_id="1176-deterministic")
    answer = str(payload.get("answer") or "")
    sources = [str(item.get("source") or "") for item in payload.get("sources") or [] if isinstance(item, dict)]

    assert "nothing in the knowledge base covers that unit's exact behaviour" in answer
    assert sources[0] == "vocal-compressor-selection.md"
    assert "Decide the job: catch occasional peaks" in answer
    assert "Find the harsh range by sweeping an EQ" not in answer


@pytest.mark.parametrize("query", [
    "My mix sounds muddy.",
    "My mix is harsh and brittle.",
    "My vocal sounds harsh and thin.",
    "My vocal is buried in the mix.",
    "My vocal is too dynamic and pumping.",
    "My vocal is over-compressed.",
    "The kick disappears when the bass comes in.",
    "My low end sounds weak.",
    "My snare sounds weak in the chorus.",
    "My drums lack punch.",
    "My mix sounds flat and has no depth.",
    "My mix sounds narrow and lacks width.",
    "My wide mix collapses in mono and sounds phasey.",
    "My mix sounds dull and too dark.",
    "My mix sounds excessively bright and harsh.",
    "My vocal track is distorted and crackling.",
    "My master is too loud and distorted.",
    "My recording has a hum and buzz.",
    "My raw vocal recording sounds bad and boxy.",
    "My vocal recording has bad room reflections.",
    "My mix has a weak stereo image and sounds narrow.",
    "My stereo image is weak.",
    "My vocal has too much sibilance.",
    "My master sounds crushed and too loud.",
    "My mix does not translate in my car and on small speakers.",
    "My master sounds worse after streaming normalization.",
    "My mix gets harsh after limiting in mastering.",
    "My low end is weak and inconsistent between notes.",
    "My chorus is too loud and the dynamics are inconsistent across the mix.",
])
def test_minimum_expert_symptoms_reach_causal_framework(query: str) -> None:
    plan = plan_for(query)
    assert plan is not None, query
    output = "\n".join(render(plan))
    assert "Most useful hypotheses to test:" in output
    assert output.count("Test:") >= 2
    assert "Verification:" in output
    assert "Most useful question:" in output


@pytest.mark.parametrize("query", [
    "My mix sounds muddy.",
    "My mix is harsh and brittle.",
    "My vocal sounds harsh and thin.",
    "My vocal is buried in the mix.",
    "The kick disappears when the bass comes in.",
    "My snare sounds weak in the chorus.",
    "My mix sounds narrow and lacks width.",
    "My mix sounds dull and too dark.",
    "My master is too loud and distorted.",
    "My vocal track is clipping digitally.",
    "My recording has a hum and buzz.",
    "My vocal has too much sibilance.",
    "My master sounds worse after streaming normalization.",
    "My mix gets harsh after limiting in mastering.",
])
def test_key_expert_symptoms_reach_public_diagnostic_answer(query: str) -> None:
    payload = answer_payload(query, allow_llm=False)
    answer = str(payload.get("answer") or "")
    assert "Diagnosis first:" in answer, (query, payload.get("route"), answer[:500])
    assert "Most useful hypotheses to test:" in answer
