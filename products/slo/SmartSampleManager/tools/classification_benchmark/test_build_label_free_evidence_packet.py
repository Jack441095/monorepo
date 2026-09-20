from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("build_label_free_evidence_packet.py")
SPEC = importlib.util.spec_from_file_location("build_label_free_evidence_packet", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _write_jsonl(path: Path, header: dict, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in [header, *rows]) + "\n", encoding="utf-8")


def _safe(record_type: str) -> dict:
    return {"record_type": record_type, "method_version": "test_v1",
            "safety": {"read_only": True, "semantic_labels_created": False,
                        "rename_actions": False}}


def test_build_joins_optional_evidence_by_path(tmp_path: Path):
    ensemble = tmp_path / "ensemble.jsonl"
    segments = tmp_path / "segments.jsonl"
    specialists = tmp_path / "specialists.jsonl"
    cards = tmp_path / "cards.json"
    path = "/library/a.wav"
    _write_jsonl(ensemble, _safe("slo_label_free_ensemble_receipt"),
                 [{"path": path, "status": "suggest", "semantic_label": None}])
    _write_jsonl(segments, _safe("slo_label_free_segment_classifier_receipt"),
                 [{"path": path, "status": "suggest", "semantic_label": None,
                   "segments": [], "n_scored_windows": 0}])
    _write_jsonl(specialists, _safe("slo_label_free_specialist_receipt"),
                 [{"path": path, "status": "suggest", "semantic_label": None,
                   "specialist_status": "scored", "specialist_suggestion": "Kick"}])
    cards.write_text(json.dumps({**_safe("slo_label_free_physical_cards"),
                                 "cards": [{"path": path, "temporal": {}}]}), encoding="utf-8")
    out = tmp_path / "packet.json"
    result = MODULE.build(ensemble, out, cards=cards, segments=segments,
                          specialists=specialists, limit=1)
    assert result["n_rows"] == 1
    row = result["rows"][0]
    assert row["review_state"] == "suggestion_review_required"
    assert row["coverage"] == {"ensemble": True, "domain_route": False,
                                "specialist": True, "name_candidate": False,
                                "physical": True, "segments": True}
    assert result["safety"]["semantic_labels_created"] is False


def test_build_joins_structured_name_candidate(tmp_path: Path):
    ensemble = tmp_path / "ensemble.jsonl"
    names = tmp_path / "names.json"
    path = "/library/a.wav"
    _write_jsonl(ensemble, _safe("slo_label_free_ensemble_receipt"),
                 [{"path": path, "status": "suggest", "semantic_label": None}])
    names.write_text(json.dumps({
        **_safe("slo_label_free_name_candidates"),
        "rows": [{"path": path, "semantic_label": None,
                  "name_state": "suggested_review_required",
                  "candidate_filename": "kick_one-shot_id-a.wav",
                  "safety": {"read_only": True, "semantic_label_created": False,
                             "rename_applied": False, "metadata_written": False}}],
    }), encoding="utf-8")
    result = MODULE.build(ensemble, tmp_path / "out.json", names=names)
    assert result["coverage"]["name_candidate"] == 1
    assert result["rows"][0]["name_candidate"]["candidate_filename"].startswith("kick_")


def test_build_rejects_mutating_source(tmp_path: Path):
    ensemble = tmp_path / "ensemble.jsonl"
    header = _safe("slo_label_free_ensemble_receipt")
    header["safety"]["rename_actions"] = True
    _write_jsonl(ensemble, header, [])
    with pytest.raises(ValueError, match="mutation"):
        MODULE.build(ensemble, tmp_path / "out.json")


def test_build_joins_optional_fused_decision(tmp_path: Path):
    ensemble = tmp_path / "ensemble.jsonl"
    fused = tmp_path / "fused.json"
    path = "/library/a.wav"
    _write_jsonl(ensemble, _safe("slo_label_free_ensemble_receipt"),
                 [{"path": path, "status": "suggest", "semantic_label": None}])
    fused.write_text(json.dumps({
        "record_type": "slo_label_free_fused_decision_receipt",
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "source_audio_modified": False,
                   "auto_action_allowed": False},
        "rows": [{"path": path, "semantic_label": None, "decision": "review",
                  "candidate_label": None, "domain": "music_sample"}],
    }), encoding="utf-8")
    result = MODULE.build(ensemble, tmp_path / "out.json", fused_decisions=fused)
    assert result["coverage"]["fused_decision"] == 1
    assert result["rows"][0]["fused_decision"]["decision"] == "review"


def test_build_joins_fft_evidence_as_review_only_measurement(tmp_path: Path):
    ensemble = tmp_path / "ensemble.jsonl"
    fft = tmp_path / "fft.json"
    path = "/library/a.wav"
    _write_jsonl(ensemble, _safe("slo_label_free_ensemble_receipt"),
                 [{"path": path, "status": "review", "semantic_label": None}])
    fft.write_text(json.dumps({
        "record_type": "slo_fft_evidence_review_queue",
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "source_audio_modified": False,
                   "training_data_created": False},
        "rows": [{"path": path, "semantic_label": None, "fft_status": "computed",
                  "fft_evidence": {"duration_s": 2.0, "sustain_ratio": 0.8,
                                    "low_band_ratio": 0.2, "mid_band_ratio": 0.5,
                                    "high_band_ratio": 0.3, "flux_mean": 0.1,
                                    "flux_std": 0.2, "flux_peak_rate": 3.0},
                  "fft_candidate_lanes": ["loop_temporal_evidence"]}],
    }), encoding="utf-8")
    result = MODULE.build(ensemble, tmp_path / "out.json", fft_evidence=fft)
    assert result["coverage"]["fft_evidence"] == 1
    evidence = result["rows"][0]["fft_evidence"]
    assert evidence["semantic_label"] is None
    assert evidence["values"]["flux_peak_rate"] == 3.0
    assert evidence["candidate_lanes"] == ["loop_temporal_evidence"]
