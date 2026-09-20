import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_physical_tag_plan.py")
SPEC = importlib.util.spec_from_file_location("build_physical_tag_plan", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_plan_preserves_physical_evidence_without_semantic_label(tmp_path):
    cards = tmp_path / "cards.json"
    cards.write_text(json.dumps({
        "record_type": "slo_audio_definition_cards",
        "cards": [{
            "path": "/a.wav",
            "source": {"analysis_duration_seconds": 1.0},
            "signal": {"rms_dbfs": -12, "peak_dbfs": -1},
            "spectrum": {"spectral_centroid_hz": 3000, "low_band_energy_ratio": 0.1, "high_band_energy_ratio": 0.4, "harmonic_energy_ratio": 0.2},
            "temporal": {"form_hint": "possibly_one_shot", "form_hint_confidence": 0.68, "estimated_tempo_bpm": 120, "periodicity_strength": 0.7},
            "pitch": {"median_f0_hz": 220, "voiced_frame_fraction": 0.8},
            "spatial": {"stereo_correlation": 1.0},
            "heuristic_tags": ["bright"], "uncertainty_reasons": [],
        }],
    }))
    out = tmp_path / "plan.jsonl"
    header = MODULE.build_plan(cards, out)
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert header["n_files"] == 1
    assert rows[1]["semantic_label"] is None
    assert "possibly_one_shot" in rows[1]["technical_tags"]
    assert "tempo_estimated" in rows[1]["technical_tags"]


def test_plan_rejects_duplicate_paths(tmp_path):
    cards = tmp_path / "cards.json"
    cards.write_text(json.dumps({"record_type": "slo_audio_definition_cards", "cards": [{"path": "/a.wav"}, {"path": "/a.wav"}]}))
    try:
        MODULE.build_plan(cards, tmp_path / "out.jsonl")
    except ValueError as exc:
        assert "duplicate paths" in str(exc)
    else:
        raise AssertionError("duplicate paths must fail closed")
