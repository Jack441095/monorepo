from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import soundfile as sf


MODULE_PATH = Path(__file__).with_name("build_fft_evidence_review_queue.py")
SPEC = importlib.util.spec_from_file_location("fft_evidence_queue", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    audio = tmp_path / "loop.wav"
    sr = 16_000
    t = np.arange(sr * 2, dtype=np.float32) / sr
    y = (0.35 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    sf.write(audio, y, sr)
    digest = hashlib.sha256(audio.read_bytes()).hexdigest()
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"files": [{
        "path": str(audio), "sha256": digest, "readable": True,
    }]}), encoding="utf-8")
    receipt = tmp_path / "receipt.jsonl"
    header = {
        "record_type": "slo_label_free_ensemble_receipt",
        "method_version": "test",
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False},
    }
    row = {
        "path": "/mnt/data/slo_training/sample_pack_testing/loop.wav",
        "content_sha256": digest, "status": "review", "semantic_label": None,
        "model_agreement": False, "model_a_status": "review", "model_b_status": "suggest",
        "model_a_margin": 0.01, "model_b_margin": 0.02,
        "evidence": {"model_a": {"view_agreement": 1.0},
                     "model_b": {"view_agreement": 1.0}},
    }
    receipt.write_text("\n".join(json.dumps(x) for x in (header, row)) + "\n", encoding="utf-8")
    return receipt, inventory


def test_queue_computes_fft_evidence_without_labels(tmp_path):
    receipt, inventory = _fixture(tmp_path)
    payload = MODULE.build_queue(receipt, inventory, tmp_path / "queue.json", limit=10)
    assert payload["n_queued"] == 1
    assert payload["n_fft_computed"] == 1
    row = payload["rows"][0]
    assert row["fft_status"] == "computed"
    assert row["semantic_label"] is None
    assert row["fft_evidence"]["duration_s"] == 2.0
    assert payload["safety"]["fft_lanes_are_evidence_only"]


def test_queue_marks_missing_audio_unresolved(tmp_path):
    receipt, inventory = _fixture(tmp_path)
    inventory.write_text(json.dumps({"files": []}), encoding="utf-8")
    payload = MODULE.build_queue(receipt, inventory, tmp_path / "queue.json", limit=10)
    assert payload["n_fft_computed"] == 0
    assert payload["n_fft_unresolved"] == 1
    assert payload["rows"][0]["fft_status"] == "unresolved_local_audio"


def test_queue_rejects_semantic_labels(tmp_path):
    receipt, inventory = _fixture(tmp_path)
    lines = receipt.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[1]); row["semantic_label"] = "Kick"; lines[1] = json.dumps(row)
    receipt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        MODULE.build_queue(receipt, inventory, tmp_path / "queue.json")
    except ValueError as exc:
        assert "semantic labels" in str(exc)
    else:
        raise AssertionError("labeled receipt was accepted")
