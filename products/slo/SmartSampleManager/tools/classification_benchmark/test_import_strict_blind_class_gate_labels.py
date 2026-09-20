from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("import_strict_blind_class_gate_labels.py")
SPEC = importlib.util.spec_from_file_location("slo_import_strict_blind_class_gate_labels", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fixture(tmp_path: Path, label: str = "Kick") -> tuple[Path, Path, Path]:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    staged = tmp_path / "staged.wav"
    staged.write_bytes(source.read_bytes())
    digest = MODULE._sha256(staged)
    review = tmp_path / "review.csv"
    _csv(review, [{
        "id": "0", "review_path": str(staged), "content_sha256": digest,
        "review_prompt": "listen", "human_label": label,
        "reviewer": "owner", "note": "heard it",
    }])
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({
        "record_type": "slo_strict_blind_class_gate_evaluator_mapping",
        "rows": [{
            "id": "0", "staged_path": str(staged), "source_path": str(source),
            "content_sha256": digest, "candidate_class": "Kick",
            "candidate_confidence": 0.9, "candidate_similarity": 0.8, "vendor": "v",
        }],
    }), encoding="utf-8")
    return review, mapping, source


def test_import_verifies_hashes_and_restores_source_path(tmp_path: Path):
    review, mapping, source = _fixture(tmp_path)
    labels, receipt = MODULE.build_labels(review, mapping, "owner")
    assert labels == [{"id": "0", "label": "Kick", "path": str(source.resolve()), "note": "heard it"}]
    assert receipt["n_usable_labels"] == 1
    assert receipt["safety"]["content_hashes_verified"] is True


def test_import_rejects_changed_staged_audio(tmp_path: Path):
    review, mapping, _ = _fixture(tmp_path)
    staged = tmp_path / "staged.wav"
    staged.write_bytes(b"changed")
    with pytest.raises(ValueError, match="staged content hash mismatch"):
        MODULE.build_labels(review, mapping, "owner")


def test_import_rejects_incomplete_labels_by_default(tmp_path: Path):
    review, mapping, _ = _fixture(tmp_path, label="")
    with pytest.raises(ValueError, match="no usable human_label"):
        MODULE.build_labels(review, mapping, "owner")
    labels, receipt = MODULE.build_labels(review, mapping, "owner", allow_incomplete=True)
    assert labels[0]["label"] == ""
    assert receipt["allow_incomplete"] is True


def test_import_rejects_non_object_mapping_root(tmp_path: Path):
    review, mapping, _ = _fixture(tmp_path)
    mapping.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="root must be a JSON object"):
        MODULE.build_labels(review, mapping, "owner")


def test_import_rejects_mapping_row_missing_identity_fields(tmp_path: Path):
    review, mapping, _ = _fixture(tmp_path)
    mapping.write_text(json.dumps({
        "record_type": "slo_strict_blind_class_gate_evaluator_mapping",
        "rows": [{"id": "0"}],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required fields"):
        MODULE.build_labels(review, mapping, "owner")
