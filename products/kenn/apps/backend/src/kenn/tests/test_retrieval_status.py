from __future__ import annotations

import json

from kenn.retrieval import retrieval


def _write_lexical_index(index_dir) -> None:
    (index_dir / "chunks.jsonl").write_text(
        json.dumps({"id": "one", "text": "kick drum"}) + "\n",
        encoding="utf-8",
    )
    (index_dir / "terms.json").write_text(
        json.dumps({"total_docs": 1, "term_counts": [{"kick": 1}], "lengths": [1]}),
        encoding="utf-8",
    )


def test_retrieval_status_reports_missing_lexical_index(tmp_path) -> None:
    status = retrieval.retrieval_status(tmp_path)

    assert status["active_mode"] == "unavailable"
    assert status["fallback_reason"] == "lexical_index_missing"
    assert status["lexical_index_available"] is False


def test_retrieval_status_exposes_bm25_fallback(tmp_path, monkeypatch) -> None:
    _write_lexical_index(tmp_path)
    monkeypatch.setattr(retrieval, "_embedding_index", None)
    monkeypatch.setattr(retrieval, "_embedding_index_error", None)
    monkeypatch.setattr(retrieval, "_embedding_model", None)
    monkeypatch.setattr(retrieval, "_embedding_model_error", None)

    status = retrieval.retrieval_status(tmp_path)

    assert status["active_mode"] == "bm25_only"
    assert status["configured_mode"] == "bm25_only"
    assert status["fallback_reason"] == "embedding_index_missing"
    assert status["degraded"] is True


def test_retrieval_status_does_not_claim_unwarmed_semantic_runtime(tmp_path, monkeypatch) -> None:
    _write_lexical_index(tmp_path)
    (tmp_path / "embeddings.npy").write_bytes(b"present-for-status-only")
    monkeypatch.setattr(retrieval, "_embedding_index", None)
    monkeypatch.setattr(retrieval, "_embedding_index_error", None)
    monkeypatch.setattr(retrieval, "_embedding_model", None)
    monkeypatch.setattr(retrieval, "_embedding_model_error", None)

    status = retrieval.retrieval_status(tmp_path)

    assert status["configured_mode"] == "hybrid"
    assert status["active_mode"] == "bm25_only"
    assert status["fallback_reason"] == "semantic_runtime_not_warmed"


def test_retrieval_status_reports_hybrid_only_after_runtime_is_ready(tmp_path, monkeypatch) -> None:
    _write_lexical_index(tmp_path)
    (tmp_path / "embeddings.npy").write_bytes(b"present-for-status-only")
    monkeypatch.setattr(retrieval, "_embedding_index", object())
    monkeypatch.setattr(retrieval, "_embedding_index_error", None)
    monkeypatch.setattr(retrieval, "_embedding_model", object())
    monkeypatch.setattr(retrieval, "_embedding_model_error", None)

    status = retrieval.retrieval_status(tmp_path)

    assert status["active_mode"] == "hybrid"
    assert status["fallback_reason"] is None
    assert status["degraded"] is False
