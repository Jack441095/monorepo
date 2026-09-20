"""Tests for thursday/ops/doc_search_ops.py (founder request, 2026-09-02).

No real ONNX model/inference here -- the module-level path constants
(EMBEDDINGS_PATH, MANIFEST_PATH, INDEX_META_PATH) and the embedder getter
are monkeypatched directly, matching task_ledger.py's established test
convention (monkeypatch.setattr(tl, "TASK_LEDGER_FILE", tmp_path / ...))
rather than an injectable-parameter pattern. What's under test is this
module's own logic: chunking, index read/write, honest degradation, and
ranking -- not the real embedding model.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

import thursday.ops.doc_search_ops as dso
from thursday.ops.structured_commands import try_dispatch


class _FakeEmbedder:
    """Deterministic fake: encodes any text to a fixed vector keyed by a
    substring match, so ranking tests can construct known "queries match
    row N exactly" scenarios without a real model.
    """

    def __init__(self, vectors: dict[str, np.ndarray]):
        self._vectors = vectors

    def encode(self, texts, *, batch_size: int = 64):
        single = isinstance(texts, str)
        items = [texts] if single else list(texts)
        result = np.array([self._vectors.get(t, np.zeros(4, dtype=np.float32)) for t in items], dtype=np.float32)
        return result[0] if single else result


@pytest.fixture
def isolated_index(monkeypatch, tmp_path):
    index_dir = tmp_path / "doc_search_index"
    monkeypatch.setattr(dso, "DOC_SEARCH_INDEX_DIR", index_dir)
    monkeypatch.setattr(dso, "EMBEDDINGS_PATH", index_dir / "embeddings.npy")
    monkeypatch.setattr(dso, "MANIFEST_PATH", index_dir / "manifest.jsonl")
    monkeypatch.setattr(dso, "INDEX_META_PATH", index_dir / "index_meta.json")
    return index_dir


# ─── Chunking ────────────────────────────────────────────────────────────


def test_chunk_markdown_respects_word_bound():
    text = "\n\n".join(f"Paragraph {i} with several words in it for padding purposes here." for i in range(20))
    chunks = dso._chunk_markdown(text, max_words=30, overlap_words=5)
    assert len(chunks) > 1
    for c in chunks[:-1]:
        assert c["word_count"] <= 35  # small tolerance for the final grouped block


def test_chunk_markdown_headings_are_their_own_boundary():
    text = "# Section One\nSome intro text.\n\n# Section Two\nMore text."
    chunks = dso._chunk_markdown(text, max_words=200, overlap_words=10)
    texts = [c["text"] for c in chunks]
    assert any("Section One" in t for t in texts)
    assert any("Section Two" in t for t in texts)


def test_chunk_markdown_tracks_line_ranges():
    text = "Line one text.\nLine two continues.\n\nLine four is new paragraph."
    chunks = dso._chunk_markdown(text, max_words=200, overlap_words=10)
    assert len(chunks) == 1
    assert chunks[0]["start_line"] == 1
    assert chunks[0]["end_line"] == 4


def test_chunk_markdown_empty_text_returns_no_chunks():
    assert dso._chunk_markdown("", max_words=200, overlap_words=10) == []


# ─── build_index / search_docs ──────────────────────────────────────────


def test_build_index_reports_evidence_missing_when_model_absent(isolated_index, monkeypatch):
    def _raise():
        raise FileNotFoundError("Embedding model not found at /fake/path.")
    monkeypatch.setattr(dso, "_get_embedder", _raise)
    result = dso.build_index()
    assert result["ok"] is False
    assert "Embedding model not found" in result["error"]


def test_keyword_is_the_supported_default_without_model():
    """Contract test for the 2026-09-18 decision: keyword is primary.
    With no embedder available (this machine: no tokenizers), a real
    question over the real corpus answers via keyword -- the semantic
    branch stays unit-tested with fakes only (see cosine test below)."""
    try:
        dso._get_embedder()
        embedder_available = True
    except (FileNotFoundError, ImportError, OSError):
        embedder_available = False
    result = dso.search_docs("beta version truth sheet", top_k=3)
    assert result["ok"] is True
    if not embedder_available:
        assert result["index_meta"]["method"] == "keyword"
    assert all(h["source"] and h["snippet"] for h in result["hits"])


def test_build_index_writes_real_files_in_sync(isolated_index, monkeypatch, tmp_path):
    # Regression test: np.save() silently appends ".npy" to any path that
    # doesn't already end with it, so a naive temp-filename choice for the
    # atomic write can write to a different path than os.replace() then
    # looks for -- found live, 2026-09-02, build_index() raised
    # FileNotFoundError on a real 144-file corpus after ~4 minutes of real
    # embedding work. This test exercises the full write path end to end.
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    (docs_root / "a.md").write_text("# Title\n\nSome real content here for testing purposes.")
    monkeypatch.setattr(dso, "_docs_root", lambda: docs_root)

    fake = _FakeEmbedder({})  # unseen texts fall back to a zero vector, fine for this test
    monkeypatch.setattr(dso, "_get_embedder", lambda: fake)

    result = dso.build_index()
    assert result["ok"] is True
    assert result["file_count"] == 1
    assert dso.EMBEDDINGS_PATH.exists()
    assert dso.MANIFEST_PATH.exists()
    assert dso.INDEX_META_PATH.exists()

    embeddings = np.load(dso.EMBEDDINGS_PATH)
    manifest_lines = dso.MANIFEST_PATH.read_text().splitlines()
    assert embeddings.shape[0] == len(manifest_lines) == result["chunk_count"]


def test_search_docs_falls_back_to_keyword_when_no_index(isolated_index, tmp_path, monkeypatch):
    """Rewritten 2026-09-18 (was ..._evidence_missing_when_no_index): the
    old expectation (error until someone runs "reindex docs") left doc
    search dead on fresh machines with no model. search_docs now falls
    back to a live keyword scan, labeled method:"keyword" so callers
    can't present it as semantic results."""
    corpus = tmp_path / "docs"
    corpus.mkdir()
    (corpus / "guide.md").write_text("# Pricing\n\nMixing starts at £180 with two revisions.")
    monkeypatch.setattr(dso, "_keyword_roots", lambda: [corpus])

    result = dso.search_docs("mixing price")
    assert result["ok"] is True
    assert result["index_meta"]["method"] == "keyword"
    assert any("guide.md" in h["source"] for h in result["hits"])
    assert any("£180" in h["snippet"] or "Mixing" in h["snippet"] for h in result["hits"])


def test_search_docs_keyword_reports_honestly_when_nothing_matches(isolated_index, tmp_path, monkeypatch):
    corpus = tmp_path / "docs"
    corpus.mkdir()
    (corpus / "guide.md").write_text("# Pricing\n\nMixing starts at £180.")
    monkeypatch.setattr(dso, "_keyword_roots", lambda: [corpus])

    result = dso.search_docs("zzzqqq nonexistent term xyz")
    assert result["ok"] is False
    assert "No documents match" in result["error"]


def test_search_docs_falls_back_to_keyword_when_model_absent_but_index_present(isolated_index, tmp_path, monkeypatch):
    """Rewritten 2026-09-18 (was ..._evidence_missing_when_model_absent):
    an index without a runnable model (no tokenizers/onnx on a fresh
    machine) now degrades to the keyword scan instead of erroring."""
    isolated_index.mkdir(parents=True)
    np.save(dso.EMBEDDINGS_PATH, np.zeros((1, 4), dtype=np.float32))
    dso.MANIFEST_PATH.write_text(json.dumps({
        "id": "a.md#0", "source": "a.md", "start_line": 1, "end_line": 1, "text": "x", "word_count": 1,
    }) + "\n")
    dso.INDEX_META_PATH.write_text(json.dumps({"built_at": "2026-09-02T00:00:00Z", "file_count": 1, "chunk_count": 1}))

    def _raise():
        raise FileNotFoundError("Embedding model not found at /fake/path.")
    monkeypatch.setattr(dso, "_get_embedder", _raise)

    corpus = tmp_path / "docs"
    corpus.mkdir()
    (corpus / "guide.md").write_text("# Mixing\n\nTwo revisions included.")
    monkeypatch.setattr(dso, "_keyword_roots", lambda: [corpus])

    result = dso.search_docs("mixing revisions")
    assert result["ok"] is True
    assert result["index_meta"]["method"] == "keyword"


def test_search_docs_reports_corrupt_index_on_row_mismatch(isolated_index):
    isolated_index.mkdir(parents=True)
    np.save(dso.EMBEDDINGS_PATH, np.zeros((3, 4), dtype=np.float32))
    dso.MANIFEST_PATH.write_text(json.dumps({
        "id": "a.md#0", "source": "a.md", "start_line": 1, "end_line": 1, "text": "x", "word_count": 1,
    }) + "\n")
    dso.INDEX_META_PATH.write_text(json.dumps({"built_at": "2026-09-02T00:00:00Z"}))

    result = dso.search_docs("anything")
    assert result["ok"] is False
    assert "corrupt" in result["error"] or "out of sync" in result["error"]


def test_search_docs_ranks_by_cosine_similarity(isolated_index, monkeypatch):
    isolated_index.mkdir(parents=True)
    # Row 0 is orthogonal to the query, row 1 exactly matches it.
    embeddings = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
    np.save(dso.EMBEDDINGS_PATH, embeddings)
    manifest = [
        {"id": "a.md#0", "source": "a.md", "start_line": 1, "end_line": 2, "text": "unrelated content", "word_count": 2},
        {"id": "b.md#0", "source": "b.md", "start_line": 5, "end_line": 6, "text": "the real match", "word_count": 3},
    ]
    with dso.MANIFEST_PATH.open("w") as f:
        for row in manifest:
            f.write(json.dumps(row) + "\n")
    dso.INDEX_META_PATH.write_text(json.dumps({"built_at": "2026-09-02T00:00:00Z"}))

    fake = _FakeEmbedder({"my query": np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)})
    monkeypatch.setattr(dso, "_get_embedder", lambda: fake)

    result = dso.search_docs("my query", top_k=2)
    assert result["ok"] is True
    assert result["hits"][0]["source"] == "b.md"
    assert result["hits"][0]["score"] > result["hits"][1]["score"]


# ─── Rendering ───────────────────────────────────────────────────────────


def test_render_doc_search_results_never_fabricates_on_error():
    out = dso.render_doc_search_results("query", {"ok": False, "error": "boom", "hits": [], "index_meta": None})
    assert "boom" in out


def test_render_doc_search_results_cites_source_and_line_range():
    result = {
        "ok": True,
        "hits": [{"source": "docs/FOO.md", "start_line": 10, "end_line": 20, "score": 0.9, "snippet": "hello"}],
        "index_meta": {"built_at": "2026-09-02T00:00:00Z"},
        "error": None,
    }
    out = dso.render_doc_search_results("query", result)
    assert "docs/FOO.md:L10-20" in out
    assert "hello" in out
    assert "not a verified or complete answer" in out


def test_render_reindex_result_reports_success():
    out = dso.render_reindex_result({"ok": True, "file_count": 10, "chunk_count": 50, "duration_s": 2.5})
    assert "10 files" in out
    assert "50 chunks" in out


# ─── Parsing ─────────────────────────────────────────────────────────────


def test_parse_search_docs_command_empty_tail_is_a_miss():
    assert dso.parse_search_docs_command("search docs:") is None
    assert dso.parse_search_docs_command("search docs") is None


def test_parse_search_docs_command_matches_prefixes():
    assert dso.parse_search_docs_command("search docs: paddle KYC") == "paddle KYC"
    assert dso.parse_search_docs_command("what does the estate say about signing keys") == "signing keys"


def test_parse_search_docs_command_unrelated_text_is_none():
    assert dso.parse_search_docs_command("totally unrelated text") is None


def test_parse_reindex_docs_command_matches():
    assert dso.parse_reindex_docs_command("reindex docs") is True
    assert dso.parse_reindex_docs_command("rebuild doc index") is True
    assert dso.parse_reindex_docs_command("totally unrelated") is None


# ─── structured_commands wiring ─────────────────────────────────────────


def test_reindex_and_search_docs_do_not_collide(isolated_index, monkeypatch):
    monkeypatch.setattr(dso, "build_index", lambda: {"ok": True, "file_count": 1, "chunk_count": 1, "duration_s": 0.1})
    monkeypatch.setattr(dso, "search_docs", lambda q, top_k=5: {"ok": True, "hits": [], "index_meta": {}, "error": None})

    reindex_result = try_dispatch("reindex docs")
    assert reindex_result is not None
    assert reindex_result[0] == "reindex_docs"

    search_result = try_dispatch("search docs: paddle KYC")
    assert search_result is not None
    assert search_result[0] == "search_docs"
