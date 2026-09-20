from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("render_label_free_name.py")
SPEC = importlib.util.spec_from_file_location("render_label_free_name", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _receipt(path: Path) -> Path:
    header = {
        "record_type": "slo_label_free_ensemble_receipt",
        "method_version": "label_free_ensemble_v1",
        "safety": {"read_only": True, "semantic_labels_created": False, "rename_actions": False},
    }
    row = {
        "path": "/tmp/example.wav", "status": "suggest", "semantic_label": None,
        "ensemble_suggestion": "Kick", "model_agreement": True,
        "model_a_score": 0.5, "model_b_score": 0.6,
        "model_a_margin": 0.1, "model_b_margin": 0.2,
        "content_sha256": "0123456789abcdef" * 4,
    }
    path.write_text("\n".join(json.dumps(x) for x in (header, row)) + "\n", encoding="utf-8")
    return path


def test_renderer_composes_deterministic_candidate_with_physical_evidence(tmp_path: Path):
    cards = {
        "record_type": "slo_audio_definition_cards",
        "safety": {"semantic_labels_created": False, "rename_actions": False},
        "cards": [{
            "path": "/tmp/example.wav", "feature_version": "definition_card_v1",
            "temporal": {"form_hint": "possibly_one_shot"},
            "pitch": {"median_f0_hz": 110.0, "voiced_frame_fraction": 0.8},
            "heuristic_tags": ["low_end_heavy", "mostly_mono"],
            "uncertainty_reasons": [],
        }],
    }
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards), encoding="utf-8")
    payload = MODULE.render(_receipt(tmp_path / "receipt.jsonl"), tmp_path / "out.json", cards_path)
    row = payload["rows"][0]
    assert row["semantic_label"] is None
    assert row["candidate_filename"] == "kick_one-shot_low-end-heavy_mostly-mono_f0-110hz_id-01234567.wav"
    assert row["safety"]["rename_applied"] is False
    assert row["name_state"] == "suggested_review_required"


def test_renderer_marks_disagreement_for_review(tmp_path: Path):
    receipt = _receipt(tmp_path / "receipt.jsonl")
    lines = receipt.read_text().splitlines()
    row = json.loads(lines[1]); row["status"] = "review"; row["ensemble_suggestion"] = None
    receipt.write_text("\n".join([lines[0], json.dumps(row)]) + "\n")
    payload = MODULE.render(receipt, tmp_path / "out.json")
    assert payload["rows"][0]["name_state"] == "review_required"
    assert payload["rows"][0]["candidate_filename"].startswith("review_")
