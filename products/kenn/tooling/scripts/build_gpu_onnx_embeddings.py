#!/usr/bin/env python3
"""Build KENN's MiniLM embeddings with a local ONNX model on a GPU.

This mirrors ``apps/backend/src/kenn/retrieval/onnx_embedder.py`` so the generated
vectors are compatible with KENN's hybrid search.  It requires only the
already-staged ONNX model and tokenizer; no model download is attempted.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


def read_chunks(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def embed_chunks(
    chunks: list[dict], *, model_path: Path, tokenizer_path: Path,
    batch_size: int, provider: str,
) -> np.ndarray:
    if not chunks:
        raise ValueError("The chunk file is empty.")
    available = ort.get_available_providers()
    if provider not in available:
        raise RuntimeError(f"Requested provider {provider!r} is unavailable; found {available}.")
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    tokenizer.enable_truncation(max_length=256)
    tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
    session = ort.InferenceSession(
        str(model_path),
        providers=[provider, "CPUExecutionProvider"] if provider != "CPUExecutionProvider" else [provider],
    )
    input_names = {item.name for item in session.get_inputs()}
    texts = [
        " ".join((str(chunk.get("title", "")), str(chunk.get("source", "")), str(chunk.get("text", ""))))
        for chunk in chunks
    ]
    vectors: list[np.ndarray] = []
    for offset in range(0, len(texts), batch_size):
        encodings = tokenizer.encode_batch(texts[offset : offset + batch_size])
        input_ids = np.array([item.ids for item in encodings], dtype=np.int64)
        attention_mask = np.array([item.attention_mask for item in encodings], dtype=np.int64)
        feeds = {"input_ids": input_ids, "attention_mask": attention_mask}
        if "token_type_ids" in input_names:
            feeds["token_type_ids"] = np.zeros_like(input_ids)
        hidden = session.run(None, feeds)[0]
        mask = attention_mask.astype(np.float32)[..., None]
        pooled = (hidden * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1e-9, None)
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        vectors.append((pooled / np.clip(norms, 1e-12, None)).astype(np.float32))
        print(f"embedded {min(offset + batch_size, len(texts))}/{len(texts)}", flush=True)
    result = np.concatenate(vectors, axis=0)
    if result.shape != (len(chunks), 384):
        raise RuntimeError(f"Unexpected embedding shape: {result.shape}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--provider", default="CUDAExecutionProvider")
    args = parser.parse_args()
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive")
    result = embed_chunks(
        read_chunks(args.chunks), model_path=args.model, tokenizer_path=args.tokenizer,
        batch_size=args.batch_size, provider=args.provider,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.output, result, allow_pickle=False)
    print(f"saved {args.output} shape={result.shape} provider={args.provider}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
