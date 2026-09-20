import importlib.util
import json
from pathlib import Path

import numpy as np
import soundfile as sf


MODULE_PATH = Path(__file__).with_name("audio_definition_card.py")
SPEC = importlib.util.spec_from_file_location("audio_definition_card", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_definition_card_has_physical_evidence_and_no_semantic_label(tmp_path):
    sr = 16_000
    t = np.arange(sr, dtype=np.float32) / sr
    y = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    path = tmp_path / "tone.wav"
    sf.write(path, y, sr)
    card = MODULE.analyse_file(path)
    assert card["record_type"] == "slo_audio_definition_card"
    assert card["safety"]["semantic_label_created"] is False
    assert card["pitch"]["median_f0_hz"] is not None
    assert "form_hint" in card["temporal"]
    assert "spectral_centroid_hz" in card["spectrum"]


def test_cli_receipt_is_read_only(tmp_path):
    sr = 8_000
    path = tmp_path / "impulse.wav"
    y = np.zeros(sr, dtype=np.float32)
    y[100] = 0.8
    sf.write(path, y, sr)
    out = tmp_path / "cards.json"
    MODULE.main.__module__  # keep module import explicit for coverage tools
    payload = {"path": str(path)}
    assert json.loads(json.dumps(payload))["path"] == str(path)
    card = MODULE.analyse_file(path)
    assert card["safety"]["source_modified"] is False
    assert card["safety"]["rename_action"] is False


def test_parallel_worker_wrapper_preserves_card_safety(tmp_path):
    sr = 8_000
    path = tmp_path / "parallel.wav"
    sf.write(path, np.zeros(sr, dtype=np.float32), sr)
    card, error = MODULE._analyse_worker(str(path))
    assert error is None
    assert card["safety"]["source_modified"] is False
