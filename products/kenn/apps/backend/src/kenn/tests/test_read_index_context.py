"""Embedded knowledge wrappers select their corpus without replacing another chat's index."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading

import numpy as np
import pytest

from kenn.core import chat_retrieval, session_memory
from kenn.retrieval import index_store, retrieval


def _write_index(directory: Path, name: str, *, embeddings=True) -> Path:
    directory.mkdir()
    (directory / "chunks.jsonl").write_text(json.dumps({"id": name, "text": name, "source": "fixture.md", "page": 0}) + "\n")
    (directory / "terms.json").write_text(json.dumps({"total_docs": 1, "term_counts": [{name: 1}], "lengths": [1]}))
    if embeddings:
        np.save(directory / "embeddings.npy", np.array([[len(name)]], dtype=np.float32))
    return directory


@pytest.fixture
def indexes(tmp_path, monkeypatch):
    caller = _write_index(tmp_path / "caller", "caller")
    alternate = _write_index(tmp_path / "alternate", "alternate")
    monkeypatch.setattr(chat_retrieval, "CHUNKS_PATH", caller / "chunks.jsonl")
    monkeypatch.setattr(chat_retrieval, "TERMS_PATH", caller / "terms.json")
    monkeypatch.setattr(retrieval, "INDEX_DIR", caller)
    monkeypatch.setattr(index_store, "INDEX_DIR", caller)
    monkeypatch.setattr(retrieval, "_embedding_index", None)
    monkeypatch.setattr(retrieval, "_embedding_index_error", None)
    monkeypatch.setattr(retrieval, "_embedding_model", object())
    monkeypatch.setattr(retrieval, "_embedding_model_error", None)
    monkeypatch.setattr(retrieval, "_get_embedding_model", lambda: pytest.fail("No model load is allowed."))
    chat_retrieval.load_chunks.cache_clear()
    retrieval.unload_embedding_index()
    yield caller, alternate
    chat_retrieval.load_chunks.cache_clear()
    retrieval.unload_embedding_index()


def test_selected_lexical_and_embedding_reads_restore_the_warm_default(indexes):
    caller, alternate = indexes
    chunks = chat_retrieval.load_chunks()
    matrix = retrieval.load_embedding_index()
    with index_store.read_index_context(alternate):
        assert chat_retrieval.load_chunks()[0]["id"] == "alternate"
        assert "alternate" in chat_retrieval.load_terms()["inverted_index"]
        assert retrieval.load_embedding_index()[0, 0] == len("alternate")
        assert retrieval.retrieval_status()["active_mode"] == "hybrid"
    assert chat_retrieval.load_chunks() is chunks
    assert retrieval.load_embedding_index() is matrix
    assert index_store.read_index_dir() == caller


def test_selected_status_does_not_borrow_the_defaults_matrix_or_error(indexes, monkeypatch):
    _, alternate = indexes
    retrieval.load_embedding_index()
    monkeypatch.setattr(retrieval, "_embedding_index_error", "caller load failed")
    assert retrieval.retrieval_status(alternate)["fallback_reason"] == "semantic_runtime_not_warmed"
    with index_store.read_index_context(alternate):
        retrieval.load_embedding_index()
        assert retrieval.retrieval_status()["active_mode"] == "hybrid"
    assert retrieval.retrieval_status()["fallback_reason"] == "embedding_index_load_failed"


def test_selected_embedding_failure_does_not_poison_another_index(indexes):
    caller, alternate = indexes
    (alternate / "embeddings.npy").write_bytes(b"invalid-array")
    with index_store.read_index_context(alternate):
        assert retrieval.load_embedding_index() is None
        assert retrieval.retrieval_status()["fallback_reason"] == "embedding_index_load_failed"
    assert retrieval.load_embedding_index() is not None
    assert retrieval.retrieval_status(caller)["active_mode"] == "hybrid"


def test_replaced_selected_embedding_artifact_is_reloaded(indexes):
    _, alternate = indexes
    with index_store.read_index_context(alternate):
        first = retrieval.load_embedding_index()
        np.save(alternate / "embeddings.npy", np.array([[123]], dtype=np.float32))
        assert retrieval.retrieval_status()["fallback_reason"] == "semantic_runtime_not_warmed"
        assert retrieval.load_embedding_index()[0, 0] == 123
        assert retrieval.load_embedding_index() is not first


def test_same_length_flat_index_replacement_keeps_text_terms_and_matrix_together(indexes):
    _, alternate = indexes
    chunks_path, terms_path = alternate / "chunks.jsonl", alternate / "terms.json"
    with index_store.read_index_context(alternate):
        first_chunks = chat_retrieval.load_chunks()
        first_terms = chat_retrieval.load_terms()
        first_matrix = retrieval.load_embedding_index()
        for path in (chunks_path, terms_path):
            previous = path.read_text()
            replacement = previous.replace("alternate", "replacing")
            assert len(previous) == len(replacement)
            path.write_text(replacement)
        np.save(alternate / "embeddings.npy", np.array([[123]], dtype=np.float32))

        assert chat_retrieval.load_chunks()[0]["id"] == "replacing"
        assert "replacing" in chat_retrieval.load_terms()["inverted_index"]
        assert "alternate" not in chat_retrieval.load_terms()["inverted_index"]
        assert retrieval.load_embedding_index()[0, 0] == 123
        assert chat_retrieval.load_chunks() is not first_chunks
        assert chat_retrieval.load_terms() is not first_terms
        assert retrieval.load_embedding_index() is not first_matrix


def test_alternate_caches_are_bounded_without_evicting_the_default(indexes, tmp_path):
    chat_retrieval.load_chunks()
    matrix = retrieval.load_embedding_index()
    for number in range(4):
        directory = _write_index(tmp_path / str(number), str(number))
        with index_store.read_index_context(directory):
            chat_retrieval.load_chunks()
            retrieval.load_embedding_index()
    assert len(retrieval._selected_embedding_indexes) == 2
    assert chat_retrieval._load_selected_index_bundle.cache_info().currsize == 2
    assert chat_retrieval._load_default_index_bundle.cache_info().currsize == 1
    assert retrieval.load_embedding_index() is matrix


def test_read_context_restores_nested_selection_after_an_exception(indexes):
    caller, alternate = indexes
    with index_store.read_index_context(alternate):
        with pytest.raises(RuntimeError):
            with index_store.read_index_context(caller):
                assert chat_retrieval.load_chunks()[0]["id"] == "caller"
                raise RuntimeError("request failed")
        assert chat_retrieval.load_chunks()[0]["id"] == "alternate"
    assert chat_retrieval.load_chunks()[0]["id"] == "caller"


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_invalid_read_override_does_not_fall_back_or_create_storage(indexes, tmp_path, kind):
    caller, _ = indexes
    invalid = tmp_path / kind
    if kind == "file":
        invalid.write_text("not an index directory")
    with pytest.raises(ValueError, match="does not exist"):
        with index_store.read_index_context(invalid):
            pytest.fail("An invalid override must not enter the caller's context.")
    assert index_store.read_index_dir() == caller
    if kind == "missing":
        assert not invalid.exists()
    assert retrieval.retrieval_status(invalid)["active_mode"] == "unavailable"


def test_threads_keep_separate_read_indexes(indexes):
    barrier = threading.Barrier(2)
    def read(directory):
        with index_store.read_index_context(directory):
            barrier.wait(timeout=2)
            return chat_retrieval.load_chunks()[0]["id"], retrieval.load_embedding_index()[0, 0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(pool.map(read, indexes))
    assert outputs == [("caller", 6), ("alternate", 9)]


def test_async_requests_keep_separate_read_indexes(indexes):
    async def read(directory):
        with index_store.read_index_context(directory):
            await asyncio.sleep(0)
            return chat_retrieval.load_chunks()[0]["id"]
    async def requests():
        return await asyncio.gather(*(read(directory) for directory in indexes))
    assert asyncio.run(requests()) == ["caller", "alternate"]


def test_same_version_label_in_different_corpora_cannot_share_semantic_cache(indexes, monkeypatch, tmp_path):
    for directory in indexes:
        chunks = [json.loads((directory / "chunks.jsonl").read_text())]
        terms = json.loads((directory / "terms.json").read_text())
        index_store.promote_index(chunks, terms, index_dir=directory, version_id="same-version")
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "memory.db")
    monkeypatch.setattr(retrieval, "embed_text", lambda text: np.array([1.0, 0.0]))
    monkeypatch.setattr(session_memory, "_L1_EXACT_CACHE", {})
    for name in ("_L2_QUERIES", "_L2_SESSION_IDS", "_L2_VERSIONS", "_L2_EVENTS", "_L2_TIMESTAMPS"):
        monkeypatch.setattr(session_memory, name, [])
    monkeypatch.setattr(session_memory, "_L2_MATRIX", None)
    versions = []
    for directory in indexes:
        with index_store.read_index_context(directory):
            assert index_store.active_version_id(directory) == "same-version"
            versions.append(session_memory._semantic_cache_version())
    assert versions[0] != versions[1]
    assert all(str(directory) not in version for directory, version in zip(indexes, versions))
    events = [{"event": "token", "token": "caller corpus advice"}]
    with index_store.read_index_context(indexes[0]):
        session_memory.save_to_semantic_cache("how to eq kick", events, session_id="project")
        assert session_memory.get_semantic_cache_hit("how to eq kick", session_id="project") == events
    with index_store.read_index_context(indexes[1]):
        assert session_memory.get_semantic_cache_hit("how to eq kick", session_id="project") is None


def test_default_semantic_cache_version_preserves_existing_keys(monkeypatch):
    monkeypatch.setattr(index_store, "active_version_id", lambda directory: "same-version")
    assert session_memory._semantic_cache_version() == f"{session_memory.SEMANTIC_CACHE_LOGIC_VERSION}:same-version"


def test_read_context_does_not_redirect_default_promotion_paths(indexes, monkeypatch):
    caller, alternate = indexes
    matrix = retrieval.load_embedding_index()
    destinations = []
    monkeypatch.setattr(retrieval, "promote_index", lambda chunks, terms, embeddings, **kwargs: destinations.append(kwargs["index_dir"]))
    with index_store.read_index_context(alternate):
        assert retrieval.INDEX_DIR == caller
        assert index_store.INDEX_DIR == caller
        assert chat_retrieval.CHUNKS_PATH == caller / "chunks.jsonl"
        assert retrieval.update_embedding_index([]) is matrix
    assert destinations == [caller]
