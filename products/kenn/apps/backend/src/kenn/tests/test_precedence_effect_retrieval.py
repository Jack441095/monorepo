from dataclasses import asdict

import pytest

from kenn.core.chat_retrieval import display_results, result_payload
from kenn.retrieval.build_index import Chunk, build_terms
from kenn.retrieval.retrieval import bm25_search, query_topics


@pytest.mark.parametrize("query", [
    "Explain the precedence effect.",
    "What is the precedence effect?",
    "Explain the Haas effect.",
])
def test_precedence_effect_displays_haas_passage_instead_of_generic_effect_note(query) -> None:
    # The indexed width passage says Haas; the query previously matched only a generic effect note.
    passages = [
        Chunk(
            id="width", source="width-example.md", page=0, kind="note",
            title="Stereo width", text="Haas delay changes stereo width and mono compatibility.",
            topics=["stereo_width"],
        ),
        Chunk(
            id="chain", source="chain-example.md", page=0, kind="note",
            title="Signal chain", text="Explain the order of each effect. Compression follows EQ.",
        ),
    ]
    results = bm25_search(query, [asdict(passage) for passage in passages], build_terms(passages))

    assert display_results(query, results)[0][1]["id"] == "width"
    assert result_payload(query, results)[0]["source"] == "width-example.md"


def test_precedence_without_audio_effect_does_not_expand_to_stereo_width() -> None:
    assert "stereo_width" not in query_topics("Which routing rule takes precedence?")
