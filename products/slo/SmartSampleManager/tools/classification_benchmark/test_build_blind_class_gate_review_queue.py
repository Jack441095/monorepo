from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("build_blind_class_gate_review_queue.py")
SPEC = importlib.util.spec_from_file_location("slo_blind_class_gate_review_queue", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _manifest(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def _row(audio: Path, row_id: int = 1) -> dict:
    return {
        "id": row_id,
        "path": str(audio),
        "candidate_class": "Kick",
        "candidate_confidence": 0.9,
        "vendor": "vendor-a",
    }


def test_export_hides_candidate_fields_and_hashes_audio(tmp_path: Path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"audio")
    receipt, rows = MODULE.build_queue(_manifest(tmp_path, [_row(audio)]))
    assert receipt["safety"]["candidate_fields_hidden"] is True
    assert receipt["safety"]["fully_blind"] is False
    assert receipt["safety"]["labels_created"] is False
    assert set(rows[0]) == set(MODULE.FIELDS)
    assert "Kick" not in json.dumps(rows)
    assert rows[0]["content_sha256"] == MODULE._sha256_file(audio)
    assert rows[0]["human_label"] == ""


def test_accepts_manifest_receipt_shape(tmp_path: Path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"audio")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "record_type": "slo_class_conditional_gate_validation_manifest",
        "items": [_row(audio)],
    }), encoding="utf-8")
    _, rows = MODULE.build_queue(manifest)
    assert len(rows) == 1


def test_rejects_duplicate_paths(tmp_path: Path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"audio")
    with pytest.raises(ValueError, match="duplicate manifest path"):
        MODULE.build_queue(_manifest(tmp_path, [_row(audio, 1), _row(audio, 2)]))


def test_rejects_missing_audio(tmp_path: Path):
    missing = tmp_path / "missing.wav"
    with pytest.raises(ValueError, match="does not exist"):
        MODULE.build_queue(_manifest(tmp_path, [_row(missing)]))
