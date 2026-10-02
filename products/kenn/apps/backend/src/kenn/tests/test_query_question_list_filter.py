from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from kenn.core import chat_retrieval
from kenn.retrieval import retrieval
from kenn.retrieval.build_index import Chunk, build_terms


@pytest.fixture
def legacy_index(monkeypatch):
    # Legacy question echoes filled the candidate windows before any answer section could reach synthesis.
    chunks = [
        Chunk(id=f"echo-{i}", source="sidechain.md", page=0, kind="note",
              title="Sidechain bass", section="Related questions",
              text="Related questions:\n- Why does bass disappear when the kick plays?").__dict__
        for i in range(85)
    ]
    chunks.extend([
        Chunk(id="body", source="sidechain.md", page=0, kind="note",
              title="Sidechain bass", section="Short answer",
              text="Use the kick as the compressor sidechain input on the bass.").__dict__,
        Chunk(id="manual", source="manual.pdf", page=1,
              text="The compressor sidechain listens to the kick while processing bass.").__dict__,
        Chunk(id="semantic", source="routing.md", page=0, kind="note",
              title="External detector", section="Try this",
              text="Choose the external input for the detector.").__dict__,
    ])
    terms = build_terms([Chunk(**chunk) for chunk in chunks])
    monkeypatch.setattr(retrieval, "load_source_feedback_scores", lambda: {})
    monkeypatch.setattr(retrieval, "load_hard_negatives", lambda: ())
    monkeypatch.setattr(retrieval, "rerank_results", lambda _query, results: results)
    return chunks, terms


@pytest.mark.parametrize("inverted", [True, False])
def test_bm25_fills_slots_with_body_sections_from_a_legacy_index(legacy_index, inverted):
    chunks, terms = legacy_index
    if not inverted:
        terms.pop("inverted_index", None)
    before = deepcopy((chunks, terms))

    results = retrieval.bm25_search("Why does bass disappear when the kick plays?", chunks, terms, limit=2)

    assert {chunk["id"] for _score, chunk in results} == {"body", "manual"}
    assert (chunks, terms) == before
    allowed = retrieval.bm25_search("bass kick", chunks, terms, allowed=lambda chunk: chunk["kind"] == "manual")
    assert [chunk["id"] for _score, chunk in allowed] == ["manual"]


@pytest.mark.parametrize("mode", ["hybrid", "missing", "mismatched", "model_unavailable"])
def test_chat_search_filters_echoes_without_misaligning_embedding_rows(legacy_index, monkeypatch, mode):
    chunks, terms = legacy_index
    embeddings = np.eye(len(chunks), 3, dtype=np.float32)
    before = embeddings.copy()
    if mode == "missing":
        embeddings = None
    elif mode == "mismatched":
        embeddings = embeddings[:-1]
    monkeypatch.setattr(retrieval, "load_embedding_index", lambda: embeddings)

    def embed(_query):
        if mode == "model_unavailable":
            raise RuntimeError("model unavailable in this fixture")
        return np.zeros(3)

    def cosine(_query, matrix):
        assert matrix is embeddings
        assert len(matrix) == len(chunks)
        # Every echo outranks the body; the last row is a relevant semantic-only hit.
        return np.array([1.0] * 85 + [0.5, 0.4, 0.9])

    monkeypatch.setattr(retrieval, "embed_text", embed)
    monkeypatch.setattr(retrieval, "cosine_similarity_scores", cosine)
    results = chat_retrieval.search("Why does bass disappear when the kick plays?", chunks, terms, limit=3)

    expected = {"body", "manual", "semantic"} if mode == "hybrid" else {"body", "manual"}
    assert {chunk["id"] for _score, chunk in results} == expected
    if embeddings is not None:
        np.testing.assert_array_equal(embeddings, before[:len(embeddings)])


def test_an_index_containing_only_question_lists_returns_no_evidence(legacy_index, monkeypatch):
    chunks, _terms = legacy_index
    chunks = chunks[:85]
    terms = build_terms([Chunk(**chunk) for chunk in chunks])
    monkeypatch.setattr(retrieval, "load_embedding_index", lambda: None)

    assert chat_retrieval.search("bass kick", chunks, terms) == []
