"""Keep generated KENN index state outside the read-only engine checkout."""

from __future__ import annotations

from pathlib import Path


def configure_index_dir(index_dir: Path) -> None:
    """Point KENN's imported retrieval modules at a writable index directory.

    KENN's source currently derives its index path from the package location.
    The public wrapper must not write into the read-only ``Audio_Too`` checkout,
    so this adapter updates the module-level path constants after import while
    leaving all engine source files untouched.
    """
    index_dir = index_dir.expanduser().resolve()
    index_dir.mkdir(parents=True, exist_ok=True)

    from kenn.core import chat as chat_module
    from kenn.core import chat_constants, chat_retrieval
    from kenn.retrieval import build_index, index_store, retrieval

    index_store.INDEX_DIR = index_dir
    retrieval.INDEX_DIR = index_dir
    retrieval.EMBEDDINGS_PATH = index_dir / "embeddings.npy"
    build_index.INDEX_DIR = index_dir
    build_index.CHUNKS_PATH = index_dir / "chunks.jsonl"
    build_index.TERMS_PATH = index_dir / "terms.json"

    chat_constants.INDEX_DIR = index_dir
    chat_constants.CHUNKS_PATH = index_dir / "chunks.jsonl"
    chat_constants.TERMS_PATH = index_dir / "terms.json"
    chat_retrieval.CHUNKS_PATH = chat_constants.CHUNKS_PATH
    chat_retrieval.TERMS_PATH = chat_constants.TERMS_PATH
    chat_module.INDEX_DIR = index_dir
    chat_module.CHUNKS_PATH = chat_constants.CHUNKS_PATH
    chat_module.TERMS_PATH = chat_constants.TERMS_PATH

    chat_retrieval._load_index_bundle.cache_clear()
    retrieval.unload_embedding_index()
