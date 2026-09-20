from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


MODULE_PATH = Path(__file__).with_name("label_free_segment_classifier.py")
SPEC = importlib.util.spec_from_file_location("label_free_segment_classifier", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_aggregate_keeps_best_window_for_each_label():
    labels = ["kick", "snare", "voice"]
    scores = np.asarray([[0.8, 0.1, 0.2], [0.3, 0.9, 0.4]], dtype=np.float32)
    result = MODULE._aggregate(labels, scores, top_k=2)
    assert [row["label"] for row in result] == ["snare", "kick"]
    assert result[0]["window_index"] == 1
    assert result[1]["window_index"] == 0


def test_read_manifest_requires_read_only_segment_receipt(tmp_path: Path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({
        "record_type": "slo_label_free_segment_manifest",
        "safety": {"read_only": True, "semantic_labels_created": False,
                    "rename_actions": False},
        "records": [{"path": "a.wav", "windows": []}],
    }), encoding="utf-8")
    header, records = MODULE._read_manifest(path)
    assert header["record_type"] == "slo_label_free_segment_manifest"
    assert records[0]["path"] == "a.wav"


def test_read_manifest_rejects_label_mutation(tmp_path: Path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({
        "record_type": "slo_label_free_segment_manifest",
        "safety": {"read_only": True, "semantic_labels_created": True,
                    "rename_actions": False},
        "records": [],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="read-only"):
        MODULE._read_manifest(path)
