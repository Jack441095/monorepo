from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("build_taxonomy_gap_adjudication_queue.py")
SPEC = importlib.util.spec_from_file_location("slo_build_taxonomy_gap_queue", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    fields = ["path", "label", "collection", "pack", "sample_family_id", "label_source"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def test_queue_keeps_owner_decision_blank(tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"audio")
    labels = tmp_path / "labels.csv"
    _write(labels, [
        {"path": str(audio), "label": "Synth One-Shot", "collection": "V", "pack": "P", "sample_family_id": "F", "label_source": "review"},
        {"path": str(tmp_path / "ignored.wav"), "label": "Kick", "collection": "V", "pack": "P", "sample_family_id": "F", "label_source": "review"},
    ])
    queue, receipt = MODULE.build_queue(labels)
    assert len(queue) == 1
    assert queue[0]["owner_label"] == ""
    assert queue[0]["decision_status"] == "pending"
    assert receipt["policy"]["candidate_options_are_not_labels"] is True


def test_queue_rejects_missing_candidate_audio(tmp_path: Path):
    labels = tmp_path / "labels.csv"
    _write(labels, [{"path": str(tmp_path / "missing.wav"), "label": "SFX", "collection": "", "pack": "", "sample_family_id": "", "label_source": ""}])
    with pytest.raises(ValueError, match="does not exist"):
        MODULE.build_queue(labels)
