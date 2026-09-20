from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

KENN_ROOT = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn"
if str(KENN_ROOT) not in sys.path:
    sys.path.insert(0, str(KENN_ROOT.parent))

from kenn.retrieval import retrieval  # noqa: E402


def test_embedding_model_uses_torch_free_onnx_backend(monkeypatch) -> None:
    """Retrieval must load the offline ONNX backend, never sentence-transformers/torch.

    Torch is ABI-incompatible with NumPy 2.x on this platform, so the old
    sentence-transformers path silently died and dropped hybrid search to pure
    BM25. The loader now uses OnnxEmbedder (onnxruntime + tokenizers), which reads
    a local model file — no network, no torch import.
    """
    from kenn.retrieval import onnx_embedder

    created: list[tuple] = []

    class FakeOnnx:
        def __init__(self, *args, **kwargs):
            created.append((args, kwargs))

    monkeypatch.setattr(onnx_embedder, "OnnxEmbedder", FakeOnnx)
    retrieval.reset_embedding_model()
    try:
        model = retrieval._get_embedding_model()
    finally:
        retrieval.reset_embedding_model()

    assert isinstance(model, FakeOnnx)
    assert created == [((), {})]  # constructed once, default local paths, no network


def test_missing_embedding_model_has_actionable_error(tmp_path) -> None:
    import pytest

    from kenn.retrieval.onnx_embedder import OnnxEmbedder

    with pytest.raises(FileNotFoundError, match="fetch_embedding_model.py"):
        OnnxEmbedder(
            model_path=tmp_path / "missing-model.onnx",
            tokenizer_path=tmp_path / "missing-tokenizer.json",
        )


def test_hybrid_search_falls_back_to_bm25_when_model_is_unavailable(monkeypatch) -> None:
    chunks = [{"id": "one", "text": "sidechain kick bass"}, {"id": "two", "text": "vocal reverb"}]
    bm25 = [(9.0, chunks[0]), (5.0, chunks[1])]
    monkeypatch.setattr(retrieval, "bm25_search", lambda *_args, **_kwargs: bm25)
    monkeypatch.setattr(retrieval, "embed_text", lambda _query: (_ for _ in ()).throw(RuntimeError("offline")))

    result = retrieval.hybrid_search(
        "sidechain bass",
        chunks,
        {},
        limit=2,
        embedding_index=np.zeros((2, 384), dtype=np.float32),
    )

    assert result == bm25


def test_hybrid_search_reranks_the_merged_candidate_set_exactly_once(monkeypatch) -> None:
    """Regression test for the compounding-rerank bug (docs/CODEBASE_AUDIT_2026-07-06.md):
    hybrid_search used to call bm25_search() (which reranked internally) and
    then rerank_results() again on the merged set — so source_trust_multiplier
    applied 3x and hard_negative_penalty 2x for any chunk reached via BM25,
    while chunks reached only through the cosine-only backfill path got just
    one pass. bm25_search's internal rerank must be skipped (rerank=False)
    for hybrid_search's own call, and rerank_results must run exactly once,
    on the full merged candidate set.
    """
    chunks = [{"id": "one", "text": "sidechain kick bass"}, {"id": "two", "text": "vocal reverb"}]
    bm25_calls: list[bool] = []

    def fake_bm25_search(_query, _chunks, _terms, limit=8, *, rerank=True):
        bm25_calls.append(rerank)
        return [(9.0, chunks[0]), (5.0, chunks[1])]

    rerank_calls: list[list[str]] = []

    def fake_rerank_results(_query, results):
        rerank_calls.append([chunk.get("id") for _score, chunk in results])
        return results

    monkeypatch.setattr(retrieval, "bm25_search", fake_bm25_search)
    monkeypatch.setattr(retrieval, "rerank_results", fake_rerank_results)
    monkeypatch.setattr(retrieval, "embed_text", lambda _query: np.zeros(384, dtype=np.float32))

    retrieval.hybrid_search(
        "sidechain bass",
        chunks,
        {},
        limit=2,
        embedding_index=np.zeros((2, 384), dtype=np.float32),
    )

    assert bm25_calls == [False], "hybrid_search must call bm25_search with rerank=False"
    assert len(rerank_calls) == 1, (
        f"rerank_results must run exactly once on the merged candidate set, ran {len(rerank_calls)}x"
    )
    assert set(rerank_calls[0]) == {"one", "two"}


def test_feedback_scores_cache_ttl(monkeypatch) -> None:
    """Verify that load_source_feedback_scores uses caching and respects TTL."""
    # Reset cache to be clean
    retrieval._feedback_scores_cache = None
    retrieval._feedback_scores_cache_time = 0.0

    import sqlite3
    connect_calls = 0

    original_connect = sqlite3.connect

    def mock_connect(*args, **kwargs):
        nonlocal connect_calls
        connect_calls += 1
        conn = original_connect(":memory:")
        conn.execute("CREATE TABLE demo_feedback (rating TEXT, sources_json TEXT)")
        conn.execute("INSERT INTO demo_feedback VALUES ('useful', '[{\"source\": \"test_source\"}]')")
        conn.commit()
        return conn

    monkeypatch.setattr(sqlite3, "connect", mock_connect)
    monkeypatch.setattr(Path, "exists", lambda self: True)

    # First call: should call sqlite3.connect
    scores_1 = retrieval.load_source_feedback_scores()
    assert connect_calls == 1
    assert scores_1.get("test_source") > 1.0

    # Second call: should use cache and NOT call connect
    scores_2 = retrieval.load_source_feedback_scores()
    assert connect_calls == 1
    assert scores_2 == scores_1

    # Fake the TTL expiration
    retrieval._feedback_scores_cache_time = 0.0
    scores_3 = retrieval.load_source_feedback_scores()
    assert connect_calls == 2

