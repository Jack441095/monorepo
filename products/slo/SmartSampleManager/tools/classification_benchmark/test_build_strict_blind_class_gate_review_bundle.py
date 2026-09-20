from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("build_strict_blind_class_gate_review_bundle.py")
SPEC = importlib.util.spec_from_file_location("slo_strict_blind_class_gate_review_bundle", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _manifest(tmp_path: Path, audio: Path) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps([{
        "id": 4,
        "path": str(audio),
        "candidate_class": "Kick",
        "candidate_confidence": 0.91,
        "candidate_similarity": 0.77,
        "vendor": "vendor-a",
    }]), encoding="utf-8")
    return path


def test_bundle_hides_candidate_and_original_path_from_review_csv(tmp_path: Path):
    source = tmp_path / "Kick_Producer_Name.wav"
    source.write_bytes(b"audio")
    output = tmp_path / "bundle"
    # Place output outside the source's directory to satisfy the safety guard.
    output = tmp_path.parent / f"bundle-{tmp_path.name}"
    receipt = MODULE.build_bundle(_manifest(tmp_path, source), output)
    rows = list(__import__("csv").DictReader((output / "review_queue.csv").open()))
    assert receipt["n_rows"] == 1
    assert "Kick" not in json.dumps(rows)
    assert str(source) not in json.dumps(rows)
    assert rows[0]["human_label"] == ""
    mapping = json.loads((output / "evaluator" / "candidate_mapping.json").read_text())
    assert mapping["rows"][0]["candidate_class"] == "Kick"
    assert mapping["rows"][0]["source_path"] == str(source.resolve())
    assert mapping["safety"]["labels_created"] is False


def test_bundle_rejects_nonempty_output(tmp_path: Path):
    source = tmp_path / "a.wav"
    source.write_bytes(b"audio")
    output = tmp_path.parent / f"bundle-{tmp_path.name}"
    output.mkdir()
    (output / "existing").write_text("x")
    with pytest.raises(ValueError, match="new and empty"):
        MODULE.build_bundle(_manifest(tmp_path, source), output)


def test_bundle_rejects_output_inside_source_directory(tmp_path: Path):
    source = tmp_path / "a.wav"
    source.write_bytes(b"audio")
    with pytest.raises(ValueError, match="inside a source-audio directory"):
        MODULE.build_bundle(_manifest(tmp_path, source), tmp_path / "nested-output")
