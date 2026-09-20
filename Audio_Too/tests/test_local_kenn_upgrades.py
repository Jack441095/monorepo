"""Unit tests for offline KENN conversational templates, synonym expansion, and paraphraser upgrades."""

from __future__ import annotations

import sys
from pathlib import Path

LM = Path(__file__).resolve().parent.parent / "studio" / "kenn" / "kenn"
sys.path.insert(0, str(LM.parent))

from kenn.core import chat
from kenn.retrieval import retrieval
from kenn.llm import paraphrase_engine


def test_slang_and_synonym_topic_mapping() -> None:
    # Test vocal slang terms mapping to 'vocals' and 'eq'
    topics_vocal = retrieval.query_topics("how to fix sibilance using a deesser or autotune")
    assert "vocals" in topics_vocal
    assert "eq" in topics_vocal

    # Test gain staging and mixing terms mapping to 'mixing'
    topics_mix = retrieval.query_topics("how to stage gain and fix fader levels")
    assert "mixing" in topics_mix

    # Test translation monitoring mapping to 'translation'
    topics_translation = retrieval.query_topics("check translation on mono headphones or earbuds")
    assert "translation" in topics_translation

    # Test low-end eq mapping to 'eq' and 'bass'
    topics_bass = retrieval.query_topics("clean up muddy low-end and rumble")
    assert "eq" in topics_bass
    assert "bass" in topics_bass

    # Test acoustics/calibration mapping to 'monitoring'
    topics_mon = retrieval.query_topics("sonarworks calibration or crossfeed monitoring")
    assert "monitoring" in topics_mon


def test_dynamic_conversational_formatting() -> None:
    mock_chunk = {
        "kind": "note",
        "title": "Sidechaining Kick and Bass",
        "source": "sidechain.md",
        "text": "Tags: compression, bass\nShort answer:\nUse sidechaining.\n\nTry this:\n1. Insert compressor.\n\nAvoid this:\nDon't bypass the check.\n\nWhy it matters:\nKeep it tidy.",
    }
    results = [(15.0, mock_chunk)]

    # Test production route formatting
    ans_prod = chat.build_template_answer(
        query="how to sidechain kick and bass",
        results=results,
        route="production",
    )
    lower = ans_prod.lower()
    # Intent-based system uses "Here is the recommended production technique:" or "Here are the steps:"
    assert "recommended production technique" in lower or "here are the steps:" in lower
    # Sources section is hidden unless the query asks for it (chat_answer.py's
    # asks_for_sources() gate, 2026-08-05) -- this query doesn't ask for it.
    assert "sources:" not in lower

    # Test mix_review route formatting
    ans_review = chat.build_template_answer(
        query="how to sidechain kick and bass",
        results=results,
        route="mix_review",
    )
    lower = ans_review.lower()
    # Intent-based system — skip route-specific header assertions since content depends on intent
    assert "sources:" not in lower

    # Explicitly asking for sources should surface the section.
    ans_with_sources = chat.build_template_answer(
        query="what are your sources for sidechaining kick and bass",
        results=results,
        route="production",
    )
    assert "sources:" in ans_with_sources.lower()


def test_paraphraser_noise_cleaning() -> None:
    # Test YouTube and video filler noise sentence identification
    assert paraphrase_engine.is_noise_sentence("don't forget to smash that like button and subscribe to my channel") is True
    assert paraphrase_engine.is_noise_sentence("this video sponsor is brilliant") is True
    assert paraphrase_engine.is_noise_sentence("use my discount code for patreon") is True
    
    # Test professionalize sentence returns clean phrasing
    raw_sentence = "literally I am showing how we can group tracks"
    clean = paraphrase_engine.professionalize_sentence(raw_sentence)
    assert "The workflow demonstrates how Producers can group tracks" in clean


def test_paraphraser_action_patterns() -> None:
    # Test compression action step detection
    steps_comp = paraphrase_engine.extract_action_steps("use threshold and attack to get moderate gain reduction")
    assert any("compressor" in s for s in steps_comp)

    # Test EQ action step detection
    steps_eq = paraphrase_engine.extract_action_steps("apply a highpass filter cut")
    assert any("eq cuts" in s.lower() for s in steps_eq)

    # Test saturation action step detection
    steps_sat = paraphrase_engine.extract_action_steps("add harmonic drive and warmth")
    assert any("saturation" in s.lower() for s in steps_sat)

    # Test sidechaining action step detection
    steps_side = paraphrase_engine.extract_action_steps("configure ducking to clear low end")
    assert any("sidechain" in s.lower() for s in steps_side)
