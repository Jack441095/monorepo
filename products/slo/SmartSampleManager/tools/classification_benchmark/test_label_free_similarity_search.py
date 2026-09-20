from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


MODULE_PATH = Path(__file__).with_name("label_free_similarity_search.py")
SPEC = importlib.util.spec_from_file_location("label_free_similarity_search", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _index(path: Path) -> Path:
    vectors = np.asarray([[1.0, 0.0], [0.99, 0.1], [0.0, 1.0]], dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    np.savez_compressed(
        path,
        record_type=np.array("slo_label_free_audio_embedding_index"),
        schema_version=np.array("1.0.0"), method_version=np.array("test"),
        model=np.array("model"), views=np.array(1),
        paths=np.asarray(["a.wav", "b.wav", "c.wav"]), embeddings=vectors,
        safety=np.array(json.dumps({"read_only": True, "semantic_labels_created": False,
                                    "rename_actions": False})),
    )
    return path


def test_search_returns_cosine_ranked_neighbors_and_excludes_self(tmp_path: Path):
    result = MODULE.search(_index(tmp_path / "index.npz"), query_index=0, top_k=2)
    assert result["top_k"] == 2
    assert result["results"][0]["path"] == "b.wav"
    assert all(item["path"] != "a.wav" for item in result["results"])
    assert result["safety"]["read_only"] is True


def test_search_rejects_non_normalized_vectors(tmp_path: Path):
    path = _index(tmp_path / "index.npz")
    z = np.load(path, allow_pickle=True)
    np.savez_compressed(path, **{k: (z[k] * 2 if k == "embeddings" else z[k]) for k in z.files})
    with pytest.raises(ValueError, match="normalized"):
        MODULE.search(path, query_index=0)


def test_search_requires_exactly_one_query(tmp_path: Path):
    with pytest.raises(ValueError, match="exactly one"):
        MODULE.search(_index(tmp_path / "index.npz"))
