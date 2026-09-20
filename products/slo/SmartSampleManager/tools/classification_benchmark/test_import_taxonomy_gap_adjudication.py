from __future__ import annotations

import csv
import hashlib
import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("import_taxonomy_gap_adjudication.py")
SPEC = importlib.util.spec_from_file_location("slo_import_taxonomy_gap", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


FIELDS = ["id", "path", "content_sha256", "observed_label", "candidate_parent_options",
          "collection", "pack", "sample_family_id", "label_source", "owner_label",
          "owner_note", "owner_reviewer", "decision_status"]


def _write(path: Path, row: dict[str, str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerow(row)


def _row(audio: Path, **updates: str) -> dict[str, str]:
    row = {field: "" for field in FIELDS}
    row.update({"id": "1", "path": str(audio), "content_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
                "observed_label": "Synth One-Shot", "candidate_parent_options": "Synth|OOD",
                "collection": "V", "pack": "P", "sample_family_id": "F",
                "label_source": "review", "owner_label": "Synth", "owner_note": "heard synth",
                "owner_reviewer": "owner", "decision_status": "approved"})
    row.update(updates); return row


def test_import_accepts_explicit_owner_decision(tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"audio")
    queue = tmp_path / "queue.csv"; _write(queue, _row(audio))
    rows, receipt = MODULE.import_decisions(queue)
    assert rows[0]["expected_subcategory"] == "Synth"
    assert rows[0]["label_authority"] == "OWNER_ADJUDICATION"
    assert receipt["imported_rows"] == 1


def test_import_rejects_unoffered_label(tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"audio")
    queue = tmp_path / "queue.csv"; _write(queue, _row(audio, owner_label="Kick"))
    with pytest.raises(ValueError, match="not an offered option"):
        MODULE.import_decisions(queue)


def test_import_allows_incomplete_only_as_skipped(tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"audio")
    queue = tmp_path / "queue.csv"; _write(queue, _row(audio, owner_label="", owner_note="", owner_reviewer="", decision_status="pending"))
    rows, receipt = MODULE.import_decisions(queue, allow_incomplete=True)
    assert rows == []
    assert receipt["skipped_incomplete_rows"] == 1
