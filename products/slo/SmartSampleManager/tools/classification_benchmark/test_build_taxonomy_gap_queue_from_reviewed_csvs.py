from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_taxonomy_gap_queue_from_reviewed_csvs.py")
SPEC = importlib.util.spec_from_file_location("slo_gap_queue_reviewed_csvs", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


FIELDS = ["path", "label", "collection", "pack", "sample_family_id", "labelling_session"]


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)


def _row(audio: Path, label: str, session: str = "session") -> dict[str, str]:
    return {"path": str(audio), "label": label, "collection": "C", "pack": "P",
            "sample_family_id": f"F-{audio.stem}", "labelling_session": session}


def test_builder_deduplicates_and_blocks_conflicts(tmp_path: Path):
    a = tmp_path / "a.wav"; a.write_bytes(b"same")
    alias = tmp_path / "alias.wav"; alias.write_bytes(b"same")
    b = tmp_path / "b.wav"; b.write_bytes(b"new")
    source = tmp_path / "labels.csv"
    _write(source, [_row(a, "Synth One-Shot"), _row(alias, "Synth One-Shot"), _row(b, "SFX")])
    queue, receipt = MODULE.build_queue([source])
    assert len(queue) == 2
    assert receipt["duplicate_alias_rows_collapsed"] == 1
    assert receipt["conflict_hashes_blocked"] == 0

    conflict = tmp_path / "conflict.csv"
    _write(conflict, [_row(a, "SFX")])
    queue, receipt = MODULE.build_queue([source, conflict])
    assert len(queue) == 1
    assert receipt["conflict_hashes_blocked"] == 1


def test_builder_excludes_base_hashes(tmp_path: Path):
    audio = tmp_path / "a.wav"; audio.write_bytes(b"same")
    source = tmp_path / "labels.csv"; _write(source, [_row(audio, "Synth One-Shot")])
    base = tmp_path / "base.json"
    base.write_text(json.dumps([{"sha256": hashlib.sha256(b"same").hexdigest()}]))
    queue, receipt = MODULE.build_queue([source], base)
    assert queue == []
    assert receipt["excluded_counts"]["already_in_base_manifest"] == 1
