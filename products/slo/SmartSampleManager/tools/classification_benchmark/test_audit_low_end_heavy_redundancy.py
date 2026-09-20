from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


MODULE_PATH = Path(__file__).with_name("audit_low_end_heavy_redundancy.py")
SPEC = importlib.util.spec_from_file_location("slo_audit_low_end_heavy_redundancy", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_audit_reports_overlap_without_creating_ground_truth(tmp_path: Path):
    cards = tmp_path / "cards.json"
    cards.write_text(json.dumps({"cards": [
        {"path": "/a.wav", "spectrum": {"low_band_energy_ratio": 0.9, "spectral_centroid_hz": 400}},
        {"path": "/b.wav", "spectrum": {"low_band_energy_ratio": 0.1, "spectral_centroid_hz": 4000}},
        {"path": "/c.wav", "spectrum": {"low_band_energy_ratio": 0.8, "spectral_centroid_hz": 3000}},
    ]}), encoding="utf-8")
    corpus = tmp_path / "corpus.npz"
    np.savez(corpus, paths=np.array(["/a.wav", "/b.wav", "/c.wav"]),
             labels=np.array(["Kick", "Hi-Hat", "Other/none"]))
    result = MODULE.audit(cards, corpus)
    assert result["n_joined"] == 3
    assert result["coverage"]["low_end_heavy_candidate_count"] == 2
    assert result["coverage"]["overlap_count"] == 1
    assert result["safety"]["attribute_ground_truth_created"] is False
    assert "do_not_ship" in result["recommendation"]


def test_audit_rejects_missing_cards(tmp_path: Path):
    cards = tmp_path / "cards.json"
    cards.write_text(json.dumps({"cards": []}), encoding="utf-8")
    corpus = tmp_path / "corpus.npz"
    np.savez(corpus, paths=np.array(["/a.wav"]), labels=np.array(["Kick"]))
    with pytest.raises(ValueError, match="non-empty cards"):
        MODULE.audit(cards, corpus)
