from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("build_label_free_specialist_scorecard.py")
SPEC = importlib.util.spec_from_file_location("build_label_free_specialist_scorecard", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_scorecard_is_explicitly_not_accuracy(tmp_path: Path):
    receipt = tmp_path / "receipt.jsonl"
    header = {"record_type": "slo_label_free_specialist_ensemble_receipt",
              "method_version": "test_v1",
              "safety": {"read_only": True, "semantic_labels_created": False, "rename_actions": False}}
    row = {"path": "/a.wav", "domain_suggestion": "music_sample", "semantic_label": None,
           "specialist_status": "scored", "status": "suggest", "specialist_model_agreement": True,
           "model_a_score": 0.4, "model_b_score": 0.5, "model_a_margin": 0.1,
           "model_b_margin": 0.2, "model_a_view_agreement": 1.0, "model_b_view_agreement": 1.0}
    receipt.write_text(json.dumps(header) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    result = MODULE.build(receipt, tmp_path / "scorecard.json")
    assert result["accuracy_claim"] is None
    assert result["auto_action_allowed"] is False
    assert result["domains"]["music_sample"]["n_model_agree"] == 1


def test_scorecard_rejects_mutating_receipt(tmp_path: Path):
    receipt = tmp_path / "receipt.jsonl"
    receipt.write_text(json.dumps({
        "record_type": "slo_label_free_specialist_receipt",
        "safety": {"read_only": True, "semantic_labels_created": False, "rename_actions": True},
    }) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="read-only"):
        MODULE.build(receipt, tmp_path / "scorecard.json")
