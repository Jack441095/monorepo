from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("build_taxonomy_gap_review_batch.py")
SPEC = importlib.util.spec_from_file_location("slo_build_taxonomy_gap_batch", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


FIELDS = ["id", "path", "content_sha256", "observed_label", "candidate_parent_options",
          "collection", "pack", "sample_family_id", "label_source", "owner_label",
          "owner_note", "owner_reviewer", "decision_status"]


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)


def _row(ident: str, group: str, collection: str, label: str = "") -> dict[str, str]:
    return {"id": ident, "path": f"/tmp/{ident}.wav", "content_sha256": ident.ljust(64, "0"),
            "observed_label": "SFX", "candidate_parent_options": group,
            "collection": collection, "pack": "P", "sample_family_id": "F",
            "label_source": "review", "owner_label": label, "owner_note": "",
            "owner_reviewer": "", "decision_status": "pending" if not label else "approved"}


def test_batch_is_breadth_first_and_excludes_completed_rows(tmp_path: Path):
    queue = tmp_path / "queue.csv"
    _write(queue, [_row("a", "Synth|OOD", "A"), _row("b", "FX|OOD", "B"),
                   _row("c", "Synth|OOD", "C"), _row("d", "FX|OOD", "D", "FX")])
    batch, receipt = MODULE.select_batch(queue, 3)
    assert len(batch) == 3
    assert {row["candidate_parent_options"] for row in batch} == {"Synth|OOD", "FX|OOD"}
    assert all(not row["owner_label"] for row in batch)
    assert receipt["pending_source_rows"] == 3


def test_batch_rejects_non_positive_limit(tmp_path: Path):
    queue = tmp_path / "queue.csv"; _write(queue, [_row("a", "Synth|OOD", "A")])
    with pytest.raises(ValueError, match="positive"):
        MODULE.select_batch(queue, 0)


def test_batch_guarantees_one_row_per_option_group(tmp_path: Path):
    queue = tmp_path / "queue.csv"
    groups = ["Synth|OOD", "Vocal Phrase|OOD", "FX|OOD"]
    rows = [_row(f"{group}-{i}", group, f"C{i}")
            for group in groups for i in range(3)]
    _write(queue, rows)
    batch, _ = MODULE.select_batch(queue, 3)
    assert {row["candidate_parent_options"] for row in batch} == set(groups)


def test_batch_excludes_hashes_from_prior_batches(tmp_path: Path):
    queue = tmp_path / "queue.csv"
    rows = [_row("a", "Synth|OOD", "A"), _row("b", "Synth|OOD", "B")]
    _write(queue, rows)
    prior = tmp_path / "prior.csv"
    _write(prior, [rows[0]])
    batch, receipt = MODULE.select_batch(queue, 10, [prior])
    assert [row["id"] for row in batch] == ["b"]
    assert receipt["excluded_pending_rows"] == 1
