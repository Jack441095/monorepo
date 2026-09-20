from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("build_label_free_embedding_ood.py")
SPEC = importlib.util.spec_from_file_location("build_label_free_embedding_ood", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_ood_receipt_is_leave_one_out_and_read_only(tmp_path: Path):
    vectors = np.array([[1.0, 0.0], [0.99, 0.1], [0.0, 1.0]], dtype=np.float32)
    index = tmp_path / "index.npz"
    np.savez(index, embeddings=vectors, paths=np.array(["/a.wav", "/b.wav", "/c.wav"]))
    out = tmp_path / "ood.json"
    result = MODULE.build(index, out, k=1)
    assert result["n_files"] == 3
    assert result["rows"][0]["path"] == "/c.wav"
    assert all(row["semantic_label"] is None for row in result["rows"])
    assert result["safety"]["auto_action_allowed"] is False


def test_ood_can_join_fused_decisions(tmp_path: Path):
    vectors = np.eye(3, dtype=np.float32)
    index = tmp_path / "index.npz"
    np.savez(index, embeddings=vectors, paths=np.array(["/a.wav", "/b.wav", "/c.wav"]))
    decisions = tmp_path / "decisions.json"
    decisions.write_text(json.dumps({
        "record_type": "slo_label_free_fused_decision_receipt",
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "auto_action_allowed": False},
        "rows": [{"path": "/a.wav", "decision": "review", "candidate_scope": "none"}],
    }), encoding="utf-8")
    result = MODULE.build(index, tmp_path / "out.json", decisions=decisions, k=1)
    joined = [row for row in result["rows"] if row["path"] == "/a.wav"][0]
    assert joined["fused_decision"] == "review"
    assert result["n_joined_decisions"] == 1
