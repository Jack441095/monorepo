"""A genre or acoustic word in the question never puts a figure into the model's instructions."""

from __future__ import annotations

import pytest

from kenn.core.acoustic_translator import ACOUSTIC_DICTIONARY
from kenn.core.chat_grounding import _measurements
from kenn.llm.llm_rewrite import build_system_prompt, format_turn_directives

# One trigger word per genre in detect_genre_from_query, and every acoustic word KENN translates.
GENRE_WORDS = ["trap", "techno", "metal", "soul", "jazz", "cinematic"]
ACOUSTIC_WORDS = sorted(ACOUSTIC_DICTIONARY)
NEUTRAL = "How should I balance this mix?"


@pytest.mark.parametrize("word", GENRE_WORDS + ACOUSTIC_WORDS)
def test_a_genre_or_acoustic_word_adds_no_figure_to_the_ollama_prompt(word: str) -> None:
    # Regression (11 Oct v4 bench): the genre profile handed over "-8.5 LUFS" and "-0.3 dBFS", acoustic guidance
    # "~40 Hz", and the gate refused them because no excerpt printed them: 10 held-out answers lost that way.
    query = f"How should I balance this {word} mix?"
    added = _measurements(build_system_prompt(route="production", query=query)) - _measurements(
        build_system_prompt(route="production", query=NEUTRAL)
    )
    assert not added, added


@pytest.mark.parametrize("word", GENRE_WORDS + ACOUSTIC_WORDS)
def test_a_genre_or_acoustic_word_adds_no_figure_to_the_mlx_directives(word: str) -> None:
    query = f"How should I balance this {word} mix?"
    added = _measurements(format_turn_directives(route="production", query=query)) - _measurements(
        format_turn_directives(route="production", query=NEUTRAL)
    )
    assert not added, added


def test_the_genre_and_acoustic_words_still_reach_the_prompt() -> None:
    prompt = build_system_prompt(route="production", query="My techno kick sounds boomy and the hats are harsh.")
    assert "Genre Target Profile (EDM / Dance / Pop): Sub-Bass Weight: heavy" in prompt
    assert "extended high-end air, tight sidechain compression" in prompt
    assert "'boomy': high-pass." in prompt
    assert "'harsh': bell cut." in prompt
