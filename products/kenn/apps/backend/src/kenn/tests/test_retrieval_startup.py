"""Regression coverage for retrieval startup degradation and auto-build."""

from __future__ import annotations

from pathlib import Path

from kenn.core import chat_retrieval
from kenn.retrieval import build_index as build_index_module
from kenn.retrieval import index_store
import kenn.server as server


def test_missing_index_returns_empty_search_bundle(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(chat_retrieval, "CHUNKS_PATH", tmp_path / "chunks.jsonl")
    monkeypatch.setattr(chat_retrieval, "TERMS_PATH", tmp_path / "terms.json")
    monkeypatch.setattr(chat_retrieval, "active_version_dir", lambda _path: None)
    chat_retrieval.load_chunks.cache_clear()

    assert chat_retrieval.load_chunks() == []
    terms = chat_retrieval.load_terms()
    assert terms["total_docs"] == 0
    assert chat_retrieval.search("compressor settings", [], terms) == []
    # The monkeypatched paths are restored after this test; do not retain the
    # empty bundle under the process-wide loader cache.
    chat_retrieval.load_chunks.cache_clear()


def test_startup_builds_notes_only_bm25_index_when_active_version_is_missing(tmp_path, monkeypatch) -> None:
    version = tmp_path / "versions" / "test-version"
    calls = {"active": 0}

    def fake_active(_index_dir: Path):
        calls["active"] += 1
        return None if calls["active"] == 1 else version

    def fake_build_index(*, pdf_dir: Path, notes_dir: Path):
        assert pdf_dir.name == ".kenn-no-pdf-source"
        assert notes_dir == build_index_module.NOTES_DIR
        assert __import__("os").environ["KENN_SKIP_EMBEDDINGS"] == "1"
        return [{"id": "note-1"}, {"id": "note-2"}]

    monkeypatch.setattr(index_store, "active_version_dir", fake_active)
    monkeypatch.setattr(build_index_module, "build_index", fake_build_index)

    result = server.ensure_retrieval_index()

    assert result == {
        "status": "built",
        "version": "test-version",
        "chunk_count": 2,
        "embeddings": False,
    }


def test_startup_continues_in_degraded_mode_when_auto_build_fails(monkeypatch) -> None:
    monkeypatch.setattr(index_store, "active_version_dir", lambda _index_dir: None)

    def fail_build(**_kwargs):
        raise SystemExit("no approved notes")

    monkeypatch.setattr(build_index_module, "build_index", fail_build)

    result = server.ensure_retrieval_index()

    assert result["status"] == "degraded"
    assert result["error"] == "no approved notes"
