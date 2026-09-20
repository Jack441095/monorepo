from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_label_free_fused_decision.py")
SPEC = importlib.util.spec_from_file_location("build_label_free_fused_decision", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _packet(tmp_path: Path, row: dict[str, object]) -> Path:
    path = tmp_path / "packet.json"
    path.write_text(json.dumps({
        "record_type": "slo_label_free_evidence_packet",
        "method_version": "packet-v1",
        "rows": [row],
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "source_audio_modified": False},
    }), encoding="utf-8")
    return path


def _row(agree: bool, specialist_label: str = "Kick") -> dict[str, object]:
    return {
        "path": "/tmp/sample.wav", "semantic_label": None,
        "domain_route": {"domain_suggestion": "music_sample", "status": "suggest",
                          "domain_margin": 0.2, "domain_score": 0.3},
        "ensemble": {"ensemble_suggestion": "Kick", "status": "suggest",
                      "model_agreement": agree, "margin_mean": 0.2,
                      "score_mean": 0.4},
        "specialist": {"domain_suggestion": "music_sample", "status": "suggest",
                       "specialist_status": "scored", "specialist_suggestion": specialist_label,
                       "margin": 0.2, "specialist_score": 0.35},
    }


def test_fusion_accepts_only_full_agreement(tmp_path: Path):
    accepted = MODULE.build(_packet(tmp_path, _row(True)), tmp_path / "accepted.json")
    assert accepted["n_suggest"] == 1
    assert accepted["rows"][0]["candidate_label"] == "Kick"
    rejected = MODULE.build(_packet(tmp_path, _row(False)), tmp_path / "rejected.json")
    assert rejected["n_suggest"] == 0
    assert "base_models_disagree" in rejected["rows"][0]["reasons"]


def test_fusion_marks_non_music_as_unknown_domain(tmp_path: Path):
    row = _row(True)
    row["domain_route"] = {"domain_suggestion": "environment_sfx", "status": "suggest",
                           "domain_margin": 0.2, "domain_score": 0.3}
    result = MODULE.build(_packet(tmp_path, row), tmp_path / "ood.json")
    assert result["n_unknown_domain"] == 1
    assert result["rows"][0]["decision"] == "unknown_domain"
    assert result["rows"][0]["candidate_scope"] == "open_world_domain"
    assert result["rows"][0]["domain_candidate_label"] == "Kick"
    assert result["safety"]["auto_action_allowed"] is False
