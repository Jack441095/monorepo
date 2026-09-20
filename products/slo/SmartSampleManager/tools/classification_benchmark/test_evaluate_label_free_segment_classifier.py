from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("evaluate_label_free_segment_classifier.py")
SPEC = importlib.util.spec_from_file_location("evaluate_label_free_segment_classifier", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_temporal_vote_prefers_repeated_evidence():
    segments = [
        {"suggestion": "Snare", "score": 0.9},
        {"suggestion": "Kick", "score": 0.6},
        {"suggestion": "Kick", "score": 0.6},
    ]
    assert MODULE._temporal_vote(segments) == "Kick"


def test_temporal_vote_abstains_without_scores():
    assert MODULE._temporal_vote([{"status": "review"}]) is None


def test_receipt_rejects_semantic_label(tmp_path: Path):
    path = tmp_path / "receipt.jsonl"
    path.write_text("\n".join([
        json.dumps({"record_type": "slo_label_free_segment_classifier_receipt",
                    "safety": {"read_only": True, "semantic_labels_created": False}}),
        json.dumps({"path": "a.wav", "semantic_label": "Kick"}),
    ]), encoding="utf-8")
    with pytest.raises(ValueError, match="semantic label"):
        MODULE._load_receipt(path, "sample_pack_testing")
