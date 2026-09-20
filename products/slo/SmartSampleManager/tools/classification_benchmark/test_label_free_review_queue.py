from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_label_free_review_queue.py")
SPEC = importlib.util.spec_from_file_location("label_free_review_queue", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _receipt(path: Path) -> Path:
    header = {
        "record_type": "slo_label_free_zero_shot_receipt",
        "method_version": "label_free_zero_shot_v1",
        "prompt_bank": {"Kick": ["kick"], "Snare": ["snare"]},
        "safety": {"read_only": True, "semantic_labels_created": False, "rename_actions": False},
    }
    rows = [
        {"path": "/tmp/uncertain.wav", "status": "review", "semantic_label": None,
         "view_agreement": 1 / 3, "margin": 0.01, "entropy": 0.6},
        {"path": "/tmp/confident.wav", "status": "review", "semantic_label": None,
         "view_agreement": 1.0, "margin": 0.2, "entropy": 0.01},
        {"path": "/tmp/suggest.wav", "status": "suggest", "semantic_label": None,
         "view_agreement": 1.0, "margin": 0.2, "entropy": 0.01},
    ]
    path.write_text("\n".join(json.dumps(item) for item in [header, *rows]) + "\n", encoding="utf-8")
    return path


def test_queue_ranks_uncertainty_and_preserves_safety(tmp_path):
    out = tmp_path / "queue.json"
    payload = MODULE.build_queue(_receipt(tmp_path / "receipt.jsonl"), out, limit=10)
    assert payload["n_review_candidates"] == 2
    assert payload["n_queued"] == 2
    assert payload["rows"][0]["path"] == "/tmp/uncertain.wav"
    assert payload["safety"]["read_only"]
    assert payload["safety"]["human_approval_required"]


def test_queue_rejects_labeled_receipt(tmp_path):
    receipt = _receipt(tmp_path / "receipt.jsonl")
    lines = receipt.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[1])
    row["semantic_label"] = "Kick"
    lines[1] = json.dumps(row)
    receipt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        MODULE.build_queue(receipt, tmp_path / "out.json")
    except ValueError as exc:
        assert "semantic labels" in str(exc)
    else:
        raise AssertionError("labeled receipt was accepted")


def test_queue_supports_ensemble_disagreement(tmp_path):
    receipt = tmp_path / "ensemble.jsonl"
    header = {
        "record_type": "slo_label_free_ensemble_receipt",
        "method_version": "label_free_ensemble_v1",
        "prompt_bank": {"Kick": ["kick"], "Snare": ["snare"]},
        "safety": {"read_only": True, "semantic_labels_created": False, "rename_actions": False},
    }
    row = {
        "path": "/tmp/disagreement.wav", "status": "review", "semantic_label": None,
        "model_agreement": False, "model_a_suggestion": "Kick", "model_b_suggestion": "Snare",
        "model_a_status": "suggest", "model_b_status": "review",
        "model_a_margin": 0.02, "model_b_margin": 0.01,
        "evidence": {"model_a": {"view_agreement": 1 / 3}, "model_b": {"view_agreement": 2 / 3}},
    }
    receipt.write_text("\n".join(json.dumps(item) for item in [header, row]) + "\n", encoding="utf-8")
    payload = MODULE.build_queue(receipt, tmp_path / "queue.json", limit=10)
    assert payload["n_review_candidates"] == 1
    reason = payload["rows"][0]["review_reason"]
    assert reason["model_disagreement"] is True
    assert reason["model_a_suggestion"] == "Kick"


def test_queue_supports_routed_specialist_receipt(tmp_path):
    receipt = tmp_path / "specialist.jsonl"
    header = {
        "record_type": "slo_label_free_specialist_receipt",
        "method_version": "label_free_specialist_classifier_v1",
        "specialist_prompt_banks": {"music_sample": {"Kick": ["kick"]}},
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False},
    }
    row = {"path": "/tmp/specialist.wav", "status": "review",
           "semantic_label": None, "domain_suggestion": "music_sample",
           "specialist_status": "scored", "specialist_suggestion": "Kick",
           "margin": 0.01, "entropy": 0.6, "view_agreement": 1.0}
    receipt.write_text("\n".join(json.dumps(item) for item in [header, row]) + "\n",
                       encoding="utf-8")
    payload = MODULE.build_queue(receipt, tmp_path / "queue.json", limit=10)
    assert payload["n_queued"] == 1
    assert payload["rows"][0]["review_reason"]["domain"] == "music_sample"
