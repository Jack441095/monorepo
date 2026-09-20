from __future__ import annotations

import csv
import hashlib
import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("merge_taxonomy_gap_queues.py")
SPEC = importlib.util.spec_from_file_location("slo_merge_taxonomy_queues", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _write(path: Path, audio: Path, label: str, owner: str = "") -> None:
    row = {field: "" for field in MODULE.FIELDS}
    row.update({"id": path.stem, "path": str(audio),
                "content_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
                "observed_label": label, "candidate_parent_options": "Synth|OOD",
                "collection": "C", "pack": "P", "sample_family_id": "F",
                "label_source": "review", "owner_label": owner,
                "owner_note": "heard synth" if owner else "",
                "owner_reviewer": "owner" if owner else "",
                "decision_status": "approved" if owner else "pending"})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.FIELDS); writer.writeheader(); writer.writerow(row)


def test_merge_deduplicates_and_carries_decision(tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"audio")
    a = tmp_path / "a.csv"; b = tmp_path / "b.csv"
    _write(a, audio, "Synth One-Shot"); _write(b, audio, "Synth One-Shot", "Synth")
    receipt = MODULE.merge_queues([a, b], tmp_path / "out.csv")
    assert receipt["merged_rows"] == 1 and receipt["duplicate_alias_rows_collapsed"] == 1
    row = next(csv.DictReader((tmp_path / "out.csv").open()))
    assert row["owner_label"] == "Synth"


def test_merge_blocks_conflicting_observations(tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"audio")
    a = tmp_path / "a.csv"; b = tmp_path / "b.csv"
    _write(a, audio, "Synth One-Shot"); _write(b, audio, "SFX")
    receipt = MODULE.merge_queues([a, b], tmp_path / "out.csv")
    assert receipt["merged_rows"] == 0 and receipt["conflict_hashes_blocked"] == 1
