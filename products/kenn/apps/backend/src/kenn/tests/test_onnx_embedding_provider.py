from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pytest

from kenn.retrieval.onnx_embedder import OnnxEmbedder


@pytest.fixture
def embedding_runtime(tmp_path, monkeypatch):
    model_path = tmp_path / "model.onnx"
    model_path.touch()
    calls = {}

    class Tokenizer:
        @classmethod
        def from_file(cls, path):
            calls["tokenizer_path"] = path
            return cls()

        def enable_truncation(self, *, max_length):
            calls["max_length"] = max_length

        def no_padding(self):
            pass

        def encode_batch(self, texts):
            return [
                SimpleNamespace(ids=[1] * len(text.split()), attention_mask=[1] * len(text.split()))
                for text in texts
            ]

    class Session:
        def __init__(self, path, *, sess_options, providers):
            calls.update(model_path=path, options=sess_options, providers=providers)

        def get_inputs(self):
            return [SimpleNamespace(name=name) for name in ("input_ids", "attention_mask", "token_type_ids")]

        def run(self, _outputs, feeds):
            calls["feeds"] = feeds
            hidden = np.zeros((*feeds["input_ids"].shape, 384), dtype=np.float32)
            hidden[:, :, :2] = [3.0, 4.0]
            # Padding must never contribute to a query vector, even if its model output is large.
            hidden[feeds["attention_mask"] == 0] = 1000.0
            return [hidden]

    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(
        SessionOptions=SimpleNamespace,
        InferenceSession=Session,
        get_available_providers=lambda: ["CoreMLExecutionProvider", "CPUExecutionProvider"],
    ))
    monkeypatch.setitem(sys.modules, "tokenizers", SimpleNamespace(Tokenizer=Tokenizer))
    monkeypatch.delenv("KENN_EMBEDDING_INTRA_OP_THREADS", raising=False)
    monkeypatch.delenv("KENN_EMBEDDING_INTER_OP_THREADS", raising=False)
    return model_path, calls


def test_short_queries_use_cpu_even_when_coreml_is_available(embedding_runtime, monkeypatch):
    # Preferring CoreML made short queries 11 times slower on the producer's M3.
    model_path, calls = embedding_runtime
    monkeypatch.setenv("KENN_EMBEDDING_INTRA_OP_THREADS", "2")
    monkeypatch.setenv("KENN_EMBEDDING_INTER_OP_THREADS", "1")

    embedder = OnnxEmbedder(model_path, model_path.with_name("tokenizer.json"), max_len=128)
    vectors = embedder.encode(["compressor ratio", "release"], normalize_embeddings=True)

    assert calls["providers"] == ["CPUExecutionProvider"]
    assert calls["options"].intra_op_num_threads == 2
    assert calls["options"].inter_op_num_threads == 1
    assert calls["model_path"] == str(model_path)
    assert calls["tokenizer_path"] == str(model_path.with_name("tokenizer.json"))
    assert calls["max_length"] == 128
    assert vectors.shape == (2, 384)
    assert vectors.dtype == np.float32
    np.testing.assert_allclose(vectors[:, :2], [[0.6, 0.8], [0.6, 0.8]])
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), [1.0, 1.0])
    np.testing.assert_array_equal(calls["feeds"]["attention_mask"], [[1, 1], [1, 0]])
    np.testing.assert_array_equal(calls["feeds"]["token_type_ids"], [[0, 0], [0, 0]])


@pytest.mark.parametrize("value", ["0", "-1", "many"])
def test_invalid_embedding_thread_budget_stops_before_session_creation(embedding_runtime, monkeypatch, value):
    model_path, calls = embedding_runtime
    monkeypatch.setenv("KENN_EMBEDDING_INTRA_OP_THREADS", value)

    with pytest.raises(ValueError, match="KENN_EMBEDDING_INTRA_OP_THREADS must be a positive integer"):
        OnnxEmbedder(model_path)

    assert "providers" not in calls
