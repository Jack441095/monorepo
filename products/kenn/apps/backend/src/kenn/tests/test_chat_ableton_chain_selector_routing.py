"""Regression coverage for Ableton Chain Selector intent and retrieval."""

from __future__ import annotations

from kenn.core.chat import answer_payload
from kenn.core.chat_routing import route_query
from kenn.retrieval.retrieval import query_topics


QUESTION = "How do I use the Chain Selector to switch plugins?"


def test_chain_selector_is_ableton_routing_not_wwise() -> None:
    topics = set(query_topics(QUESTION))

    assert "routing" in topics
    assert "wwise" not in topics
    assert "game_audio" not in topics
    assert route_query(QUESTION, None) == "ableton"


def test_chain_selector_answer_uses_matching_ableton_note_first() -> None:
    # The deterministic answer path is what this retrieval regression tests;
    # LLM-enabled calls may legitimately use a previously persisted semantic
    # cache owned by another test or local app session.
    result = answer_payload(QUESTION, allow_llm=False)

    assert result.get("found") is True
    assert result.get("weak_match") is not True
    sources = result.get("sources") or []
    assert sources
    assert sources[0].get("source") == "ableton-racks-and-chain-selectors.md"
    assert all("wwise" not in str(source.get("source", "")).lower() for source in sources)


def test_link_questions_route_to_the_dedicated_ableton_note() -> None:
    for question in ("What is Ableton Link?", "Does Ableton Link send audio?"):
        topics = set(query_topics(question))
        assert "ableton_link" in topics
        assert route_query(question, None) == "ableton"

        result = answer_payload(question, allow_llm=False)
        sources = result.get("sources") or []
        assert result.get("found") is True
        assert sources
        assert sources[0].get("source") == "ableton-link-sync.md"
