from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest


MODULE_PATH = Path(__file__).with_name("build_label_free_retrieval_evidence.py")
SPEC = importlib.util.spec_from_file_location("build_label_free_retrieval_evidence", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_retrieval_excludes_exact_filename_overlap(tmp_path: Path):
    query = tmp_path / "query.npz"
    reference = tmp_path / "reference.npz"
    np.savez(query, model=np.asarray("test-model"),
             embeddings=np.asarray([[1.0, 0.0]], dtype=np.float32),
             paths=np.asarray(["/q/a.wav"]))
    np.savez(reference,
             model=np.asarray("test-model"),
             embeddings=np.asarray([[1.0, 0.0], [0.99, 0.1]], dtype=np.float32),
             labels=np.asarray(["Kick", "Snare"]),
             filenames=np.asarray(["a.wav", "b.wav"]))
    result = MODULE.build(query, reference, tmp_path / "out.json", top_k=1,
                          min_similarity=0.0, min_margin=0.0)
    row = result["rows"][0]
    assert result["n_exact_filename_overlaps"] == 1
    assert row["retrieval_neighbors"][0]["filename"] == "b.wav"
    assert row["semantic_label"] is None


def test_rejects_mismatched_reference(tmp_path: Path):
    query = tmp_path / "query.npz"
    reference = tmp_path / "reference.npz"
    np.savez(query, model=np.asarray("test-model"), embeddings=np.ones((1, 2), dtype=np.float32), paths=np.asarray(["a.wav"]))
    np.savez(reference, model=np.asarray("test-model"), embeddings=np.ones((2, 2), dtype=np.float32),
             labels=np.asarray(["Kick"]), filenames=np.asarray(["a.wav"]))
    with pytest.raises(ValueError, match="lengths differ"):
        MODULE.build(query, reference, tmp_path / "out.json")


def test_rejects_mismatched_feature_spaces(tmp_path: Path):
    query = tmp_path / "query.npz"
    reference = tmp_path / "reference.npz"
    np.savez(query, model=np.asarray("clap"), embeddings=np.ones((1, 2), dtype=np.float32), paths=np.asarray(["a.wav"]))
    np.savez(reference, model=np.asarray("panns"), embeddings=np.ones((1, 2), dtype=np.float32),
             labels=np.asarray(["Kick"]), filenames=np.asarray(["b.wav"]))
    with pytest.raises(ValueError, match="different feature spaces"):
        MODULE.build(query, reference, tmp_path / "out.json")
