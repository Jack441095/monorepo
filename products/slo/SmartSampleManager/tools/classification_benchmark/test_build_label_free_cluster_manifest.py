from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


MODULE_PATH = Path(__file__).with_name("build_label_free_cluster_manifest.py")
SPEC = importlib.util.spec_from_file_location("build_label_free_cluster_manifest", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_build_clusters_and_noise(tmp_path: Path):
    embeddings = np.asarray([
        [1.0, 0.0], [0.99, 0.1], [0.98, 0.15],
        [0.0, 1.0], [0.1, 0.99], [0.15, 0.98],
        [-1.0, 0.0],
    ], dtype=np.float32)
    source = tmp_path / "index.npz"
    np.savez(source, embeddings=embeddings,
             paths=np.asarray([f"{i}.wav" for i in range(len(embeddings))]))
    out = tmp_path / "clusters.json"
    result = MODULE.build(source, out, eps=0.03, min_samples=3)
    assert result["n_rows"] == 7
    assert result["n_clusters"] == 2
    assert result["n_noise"] == 1
    assert result["safety"]["semantic_labels_created"] is False
    assert all(row["semantic_label"] is None for row in result["rows"])


def test_rejects_mismatched_index(tmp_path: Path):
    source = tmp_path / "bad.npz"
    np.savez(source, embeddings=np.ones((2, 2), dtype=np.float32), paths=np.asarray(["a.wav"]))
    with pytest.raises(ValueError, match="lengths differ"):
        MODULE.build(source, tmp_path / "out.json")
