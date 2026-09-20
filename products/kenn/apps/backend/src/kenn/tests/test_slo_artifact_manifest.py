from __future__ import annotations

import hashlib
import json

from kenn.core.slo_artifact_manifest import CONTRACT_SCHEMA, SCHEMA, inspect_manifest_file, validate_manifest


def _digest(path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(tmp_path) -> dict:
    paths = {}
    for name, content in {
        "model.onnx": b"model", "labels.json": b'["kick"]', "preprocess.json": b'{}',
        "evaluation.json": b'{"audio_only": true}', "calibration.json": b'{}',
    }.items():
        path = tmp_path / name
        path.write_bytes(content)
        paths[name] = path
    return {
        "schema": SCHEMA,
        "contract_schema": CONTRACT_SCHEMA,
        "model_id": "slo-audio-v1",
        "inference_version": "1",
        "model": {"path": "model.onnx", "sha256": _digest(paths["model.onnx"]), "format": "onnx"},
        "label_map": {"path": "labels.json", "sha256": _digest(paths["labels.json"])},
        "preprocessing": {"path": "preprocess.json", "sha256": _digest(paths["preprocess.json"])},
        "evaluation_receipt": {"path": "evaluation.json", "sha256": _digest(paths["evaluation.json"])},
        "calibration": {"path": "calibration.json", "sha256": _digest(paths["calibration.json"])},
        "evaluation": {"split_strategy": "artist_and_pack_disjoint", "audio_only": {"accuracy": 0.886, "macro_f1": 0.893}},
        "limitations": ["Advisory only; low-confidence and OOD samples remain Unknown."],
    }


def test_slo_manifest_validates_and_hashes_export_files(tmp_path) -> None:
    payload = _manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    result = inspect_manifest_file(manifest_path)

    assert validate_manifest(payload)["advisory_only"] is True
    assert result["status"] == "verified"
    assert result["all_files_verified"] is True
    assert result["promotion_eligible"] is False
    assert result["manifest"]["evaluation"]["audio_only"]["macro_f1"] == 0.893


def test_slo_manifest_rejects_bad_hash_or_missing_limitations(tmp_path) -> None:
    payload = _manifest(tmp_path)
    payload["model"]["sha256"] = "sha256:" + "0" * 64
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    mismatch = inspect_manifest_file(manifest_path)
    assert mismatch["status"] == "manifest_valid_files_unverified"
    assert mismatch["all_files_verified"] is False

    payload["limitations"] = []
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    assert inspect_manifest_file(manifest_path, verify_files=False)["status"] == "invalid"


def test_slo_manifest_requires_the_kenn_adapter_contract(tmp_path) -> None:
    payload = _manifest(tmp_path)
    payload.pop("contract_schema")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    result = inspect_manifest_file(manifest_path, verify_files=False)

    assert result["status"] == "invalid"
    assert "contract_schema" in result["error"]
