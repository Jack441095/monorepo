from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from build_breadth_target_corpus import build


def _write_labels(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "label", "percussion_subtype", "rejection_reason"])
        writer.writeheader()
        writer.writerows(rows)


def _write_embedding(path: Path, paths: list[str], values: list[list[float]]) -> None:
    np.savez(path, paths=np.asarray(paths, dtype=object), emb=np.asarray(values, dtype=np.float32),
             errors=np.asarray([""] * len(paths), dtype=object))


def _write_base(path: Path, paths: list[str], labels: list[str], values: list[list[float]]) -> None:
    np.savez(path, paths=np.asarray(paths, dtype=object), labels=np.asarray(labels, dtype=object),
             emb=np.asarray(values, dtype=np.float32), source=np.asarray(["base"] * len(paths), dtype=object),
             percussion_subtype=np.asarray([""] * len(paths), dtype=object),
             rejection_reason=np.asarray([""] * len(paths), dtype=object))


def test_exact_target_and_human_overlap_correction(tmp_path: Path):
    a = tmp_path / "a.wav"; b = tmp_path / "b.wav"; c = tmp_path / "c.wav"
    for path in (a, b, c): path.write_bytes(b"test")
    labels = tmp_path / "labels.csv"
    _write_labels(labels, [
        {"path": str(a), "label": "Clap", "percussion_subtype": "", "rejection_reason": ""},
        {"path": str(b), "label": "Synth One-Shot", "percussion_subtype": "", "rejection_reason": ""},
    ])
    emb = tmp_path / "emb.npz"
    _write_embedding(emb, [str(a), str(b)], [[1, 0], [0, 1]])
    base = tmp_path / "base.npz"
    _write_base(base, [str(a)], ["Crash"], [[1, 0]])
    payload, receipt = build(base, labels, emb, 2, True)
    assert receipt["n_human_corrections_overlapping_base"] == 1
    assert receipt["n_appended_rows"] == 1
    rows = {str(p): str(label) for p, label in zip(payload["paths"], payload["labels"])}
    assert rows[str(a)] == "Clap"
    assert rows[str(b)] == "Other/none"
    assert payload["raw_labels"].tolist() == ["Clap", "Synth One-Shot"]


def test_target_is_fail_closed(tmp_path: Path):
    a = tmp_path / "a.wav"; a.write_bytes(b"test")
    labels = tmp_path / "labels.csv"
    _write_labels(labels, [{"path": str(a), "label": "Kick", "percussion_subtype": "", "rejection_reason": ""}])
    emb = tmp_path / "emb.npz"; _write_embedding(emb, [str(a)], [[1, 0]])
    base = tmp_path / "base.npz"; _write_base(base, [], [], np.empty((0, 2)))
    with pytest.raises(ValueError, match="target requires exactly"):
        build(base, labels, emb, 2, False)


def test_missing_embedding_is_fail_closed(tmp_path: Path):
    a = tmp_path / "a.wav"; a.write_bytes(b"test")
    labels = tmp_path / "labels.csv"
    _write_labels(labels, [{"path": str(a), "label": "Kick", "percussion_subtype": "", "rejection_reason": ""}])
    emb = tmp_path / "emb.npz"; _write_embedding(emb, [], [])
    base = tmp_path / "base.npz"; _write_base(base, [], [], np.empty((0, 2)))
    with pytest.raises(ValueError, match="no embedding"):
        build(base, labels, emb, 1, False)


def test_overlap_can_reuse_base_embedding(tmp_path: Path):
    a = tmp_path / "a.wav"; a.write_bytes(b"test")
    labels = tmp_path / "labels.csv"
    _write_labels(labels, [{"path": str(a), "label": "Clap", "percussion_subtype": "", "rejection_reason": ""}])
    emb = tmp_path / "emb.npz"; _write_embedding(emb, [], [])
    base = tmp_path / "base.npz"; _write_base(base, [str(a)], ["Crash"], [[1, 2]])
    payload, receipt = build(base, labels, emb, 1, False)
    assert receipt["n_human_corrections_overlapping_base"] == 1
    assert payload["emb"].tolist() == [[1.0, 2.0]]
    assert payload["labels"].tolist() == ["Clap"]
