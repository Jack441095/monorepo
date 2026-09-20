
#!/usr/bin/env python3
"""Incrementally update the embedding index after new notes are approved.

Usage:
    python KENN/update_embedding_index.py [--chunk-ids id1 id2 ...]

If no chunk IDs are given, the script reads the current chunks.jsonl and
compares against the embedding index size to find new chunks automatically.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = ROOT / "data" / "index"
CHUNKS_PATH = INDEX_DIR / "chunks.jsonl"
EMBEDDINGS_PATH = INDEX_DIR / "embeddings.npy"


def find_new_chunks() -> list[dict]:
    """Find chunks that don't yet have embeddings."""
    chunks = _load_chunks()
    try:
        import numpy as np
        from kenn.retrieval.index_store import active_artifact_path

        existing = np.load(
            str(active_artifact_path("embeddings.npy", INDEX_DIR)), allow_pickle=False
        )
        existing_count = existing.shape[0]
    except Exception:
        existing_count = 0

    if len(chunks) <= existing_count:
        print(f"  Embedding index is up-to-date ({existing_count} chunks).")
        return []

    new_chunks = chunks[existing_count:]
    print(f"  Found {len(new_chunks)} new chunk(s) to embed.")
    return new_chunks


def _load_chunks() -> list[dict]:
    from kenn.retrieval.index_store import active_artifact_path

    chunks_path = active_artifact_path("chunks.jsonl", INDEX_DIR)
    if not chunks_path.exists():
        return []
    with chunks_path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def update(chunk_ids: list[str] | None = None) -> int:
    from kenn.retrieval.retrieval import update_embedding_index

    if chunk_ids:
        all_chunks = _load_chunks()
        id_set = set(chunk_ids)
        new_chunks = [c for c in all_chunks if c.get("id") in id_set]
        if not new_chunks:
            print(f"  No chunks found with the given IDs: {chunk_ids}")
            return 0
        print(f"  Found {len(new_chunks)} chunk(s) by ID.")
    else:
        new_chunks = find_new_chunks()

    if not new_chunks:
        print("  Nothing to update.")
        return 0

    update_embedding_index(new_chunks)
    print(f"  Embedding index updated with {len(new_chunks)} new chunk(s).")
    return len(new_chunks)


if __name__ == "__main__":
    args = sys.argv[1:]
    chunk_ids = None
    if args and args[0] == "--chunk-ids":
        chunk_ids = args[1:]
    updated = update(chunk_ids)
    sys.exit(0 if updated or updated == 0 else 1)
