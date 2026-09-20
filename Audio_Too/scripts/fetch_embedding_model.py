#!/usr/bin/env python3
"""Fetch the torch-free ONNX embedding model for KENN semantic search.

KENN's retrieval uses an ONNX export of all-MiniLM-L6-v2 (via onnxruntime +
tokenizers) instead of sentence-transformers/torch, because Torch is
ABI-incompatible with the NumPy 2.x that AudioGen requires on this platform.

The model (~90 MB) and tokenizer are git-ignored; run this once after setup:

    python scripts/fetch_embedding_model.py

Then rebuild the embedding index:

    python scripts/fetch_embedding_model.py --rebuild-index
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _resumable_download import download  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
MONOREPO = REPO.parent
MODEL_DIR = MONOREPO / "products" / "kenn" / "kenn" / "artifacts" / "models" / "minilm"
BASE = "https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main"
FILES = {
    "model.onnx": f"{BASE}/onnx/model.onnx",
    "tokenizer.json": f"{BASE}/tokenizer.json",
}


def fetch() -> None:
    for name, url in FILES.items():
        dest = MODEL_DIR / name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"  {name}: already present, skipping")
            continue
        download(url, dest)


def rebuild_index() -> None:
    sys.path.insert(0, str(REPO))
    from kenn.core.chat import load_chunks
    from kenn.retrieval import retrieval as R

    chunks = load_chunks()
    R.unload_embedding_index()
    embeddings = R.embed_chunks(chunks, batch_size=64)
    R.save_embedding_index(embeddings)
    print(f"rebuilt embeddings.npy: {embeddings.shape} for {len(chunks)} chunks")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild-index", action="store_true", help="rebuild embeddings.npy after fetch")
    args = parser.parse_args()
    print("Fetching ONNX embedding model...")
    fetch()
    if args.rebuild_index:
        print("Rebuilding embedding index...")
        rebuild_index()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
