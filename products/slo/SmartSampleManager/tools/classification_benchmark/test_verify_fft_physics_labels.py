from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "verify_fft_physics_labels",
    Path(__file__).with_name("verify_fft_physics_labels.py"),
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _write_fixture(tmp_path: Path, label: str = "Kick", note: str = ""):
    audio = tmp_path / "tone.wav"
    audio.write_bytes(b"stable-audio-fixture")
    digest = hashlib.sha256(audio.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "record_type": "slo_fft_physics_label_manifest",
        "rows": [{"id": "fftphys-0001", "path": str(audio),
                   "content_sha256": digest}],
    }))
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "id", "path", "label", "note", "not_in_list_label",
        ])
        writer.writeheader()
        writer.writerow({"id": "fftphys-0001", "path": str(audio),
                         "label": label, "note": note,
                         "not_in_list_label": ""})
    return manifest, labels


def test_valid_label_is_verified(tmp_path: Path):
    manifest, labels = _write_fixture(tmp_path)
    receipt = MODULE.verify_labels(manifest, labels)
    assert receipt["decision"] == "verified_review_only"
    assert receipt["summary"]["accepted_labeled_rows"] == 1
    assert not receipt["failures"]


def test_required_escape_note_is_fail_closed(tmp_path: Path):
    manifest, labels = _write_fixture(tmp_path, label="Unknown")
    receipt = MODULE.verify_labels(manifest, labels)
    assert receipt["decision"] == "rejected_fail_closed"
    assert receipt["failures"][0]["reason"] == "required_escape_note_missing"


def test_candidate_columns_are_rejected(tmp_path: Path):
    manifest, labels = _write_fixture(tmp_path)
    with labels.open("a", newline="") as handle:
        # Rebuild the file with an explicitly forbidden column.
        rows = list(csv.DictReader(labels.open()))
    with labels.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "id", "path", "label", "note", "not_in_list_label", "fft_score",
        ])
        writer.writeheader()
        writer.writerow({**rows[0], "fft_score": "0.9"})
    with pytest.raises(ValueError, match="candidate/evidence"):
        MODULE.verify_labels(manifest, labels)


def test_hash_change_is_rejected(tmp_path: Path):
    manifest, labels = _write_fixture(tmp_path)
    audio = tmp_path / "tone.wav"
    audio.write_bytes(b"changed-audio")
    receipt = MODULE.verify_labels(manifest, labels)
    assert receipt["failures"][0]["reason"] == "content_hash_mismatch"


def test_duplicate_blank_id_is_rejected(tmp_path: Path):
    manifest, labels = _write_fixture(tmp_path, label="")
    with labels.open("a", newline="") as handle:
        handle.write("fftphys-0001,\"" + str(tmp_path / "tone.wav") + "\",,,\n")
    receipt = MODULE.verify_labels(manifest, labels)
    assert any(item["reason"] == "duplicate_id" for item in receipt["failures"])
