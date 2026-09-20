"""Torch-free ONNX embedding backend for KENN retrieval (all-MiniLM-L6-v2).

Why this exists: sentence-transformers pulls in PyTorch, and on this platform
Torch 2.2 is ABI-incompatible with NumPy 2.x (which AudioGen's realtime player
requires), so `torch.from_numpy` raises and the embedding path silently dies —
which is why KENN's hybrid search was falling back to pure BM25.

This backend uses onnxruntime + the Rust `tokenizers` library only (no torch),
and reproduces sentence-transformers' all-MiniLM-L6-v2 output exactly:
mean-pooling over token embeddings with the attention mask, then L2 normalization.

The model file (`model.onnx`, ~90 MB) is git-ignored; fetch it with
`scripts/fetch_embedding_model.py`. The tokenizer ships alongside it.
"""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path

import numpy as np

# A process-wide lock serializing ONNX InferenceSession creation (session
# init has been observed to be unsafe under concurrent construction). This
# was previously imported from an external `audio_too` package that does
# not exist in this standalone repository; this is the KENN-owned
# equivalent -- just a shared lock, not a real dependency on anything else
# in that package.
ONNX_SESSION_INIT_LOCK = threading.Lock()

_MODEL_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "models" / "minilm"
_MODEL_PATH = _MODEL_DIR / "model.onnx"
_TOKENIZER_PATH = _MODEL_DIR / "tokenizer.json"
_EMBED_DIM = 384
_MAX_LEN = 256


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def embedding_model_identity() -> dict:
    """Return stable model identity recorded in reproducible index manifests."""
    return {
        "id": "Xenova/all-MiniLM-L6-v2",
        "backend": "onnxruntime",
        "dimensions": _EMBED_DIM,
        "max_tokens": _MAX_LEN,
        "model_sha256": _sha256(_MODEL_PATH) if _MODEL_PATH.is_file() else "",
        "tokenizer_sha256": _sha256(_TOKENIZER_PATH) if _TOKENIZER_PATH.is_file() else "",
    }


def _positive_thread_count(value: str, name: str) -> int:
    try:
        count = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if count <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return count


class OnnxEmbedder:
    """Drop-in replacement for the subset of the SentenceTransformer API that
    KENN retrieval uses: ``.encode(text_or_list, normalize_embeddings=True)``."""

    def __init__(
        self,
        model_path: Path = _MODEL_PATH,
        tokenizer_path: Path = _TOKENIZER_PATH,
        max_len: int = _MAX_LEN,
    ) -> None:
        if not Path(model_path).exists():
            raise FileNotFoundError(
                f"ONNX embedding model missing at {model_path}. "
                "Run: python scripts/fetch_embedding_model.py"
            )
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.enable_truncation(max_length=max_len)
        self._tokenizer.no_padding()
        session_options = ort.SessionOptions()
        intra_op_threads = os.environ.get("KENN_EMBEDDING_INTRA_OP_THREADS", "").strip()
        inter_op_threads = os.environ.get("KENN_EMBEDDING_INTER_OP_THREADS", "").strip()
        if intra_op_threads:
            session_options.intra_op_num_threads = _positive_thread_count(
                intra_op_threads, "KENN_EMBEDDING_INTRA_OP_THREADS"
            )
        if inter_op_threads:
            session_options.inter_op_num_threads = _positive_thread_count(
                inter_op_threads, "KENN_EMBEDDING_INTER_OP_THREADS"
            )

        available_providers = ort.get_available_providers()
        preferred_providers = [
            p for p in ["CoreMLExecutionProvider", "CPUExecutionProvider"]
            if p in available_providers
        ] or ["CPUExecutionProvider"]

        with ONNX_SESSION_INIT_LOCK:
            self._session = ort.InferenceSession(
                str(model_path),
                sess_options=session_options,
                providers=preferred_providers,
            )
        self._input_names = {i.name for i in self._session.get_inputs()}

    def encode(
        self,
        texts,
        *,
        normalize_embeddings: bool = True,
        batch_size: int = 64,
        show_progress_bar: bool = False,  # accepted for API parity, ignored
        **_ignored,
    ) -> np.ndarray:
        single = isinstance(texts, str)
        items = [texts] if single else list(texts)
        if not items:
            return np.zeros((0, _EMBED_DIM), dtype=np.float32)
        chunks = [
            self._encode_batch(items[i : i + batch_size], normalize_embeddings)
            for i in range(0, len(items), batch_size)
        ]
        result = np.vstack(chunks)
        return result[0] if single else result

    def _encode_batch(self, batch: list[str], normalize: bool) -> np.ndarray:
        encodings = self._tokenizer.encode_batch(batch)
        max_batch_len = max(len(e.ids) for e in encodings) if encodings else 1
        input_ids_list = []
        mask_list = []
        for e in encodings:
            ids = list(e.ids)
            mask = list(e.attention_mask)
            if len(ids) < max_batch_len:
                diff = max_batch_len - len(ids)
                ids.extend([0] * diff)
                mask.extend([0] * diff)
            input_ids_list.append(ids)
            mask_list.append(mask)

        input_ids = np.array(input_ids_list, dtype=np.int64)
        attention_mask = np.array(mask_list, dtype=np.int64)
        feeds = {"input_ids": input_ids, "attention_mask": attention_mask}
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = np.zeros_like(input_ids)

        last_hidden = self._session.run(None, feeds)[0]  # [B, T, 384]

        mask = attention_mask.astype(np.float32)[..., None]  # [B, T, 1]
        summed = (last_hidden * mask).sum(axis=1)  # [B, 384]
        counts = np.clip(mask.sum(axis=1), 1e-9, None)  # [B, 1]
        embeddings = summed / counts
        if normalize:
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            embeddings = embeddings / np.clip(norms, 1e-12, None)
        return embeddings.astype(np.float32)
