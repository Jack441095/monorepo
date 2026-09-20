from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import soundfile as sf


MODULE_PATH = Path(__file__).with_name("build_label_free_segment_manifest.py")
SPEC = importlib.util.spec_from_file_location("build_label_free_segment_manifest", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_manifest_batches_cards_and_preserves_logical_paths(tmp_path: Path):
    audio = tmp_path / "a.wav"
    y = np.zeros(16_000, dtype=np.float32); y[100:1_000] = 0.8
    sf.write(audio, y, 16_000)
    cards = {
        "record_type": "slo_label_free_physical_cards",
        "safety": {"read_only": True, "semantic_labels_created": False, "rename_actions": False},
        "cards": [{"path": "/logical/a.wav", "analysis_path": str(audio)}],
    }
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards), encoding="utf-8")
    payload = MODULE.build(cards_path, tmp_path / "manifest.json", limit=1)
    assert payload["n_requested"] == payload["n_segmented"] == 1
    assert payload["records"][0]["path"] == "/logical/a.wav"
    assert payload["records"][0]["windows"]
    assert payload["safety"]["semantic_labels_created"] is False
