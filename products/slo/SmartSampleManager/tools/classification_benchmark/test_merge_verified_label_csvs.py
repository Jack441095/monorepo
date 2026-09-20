from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("merge_verified_label_csvs.py")
SPEC = importlib.util.spec_from_file_location("merge_verified_label_csvs", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "label"])
        writer.writeheader()
        writer.writerows(rows)


def test_merge_collapses_identical_and_excludes_conflicts(tmp_path: Path):
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    _write(a, [{"path": "/x/sample_pack_testing/a.wav", "label": "Kick"},
               {"path": "/x/sample_pack_testing/b.wav", "label": "Snare"}])
    _write(b, [{"path": "/y/sample_pack_testing/a.wav", "label": "Kick"},
               {"path": "/y/sample_pack_testing/b.wav", "label": "Clap"},
               {"path": "/y/sample_pack_testing/c.wav", "label": "Foley"}])
    report = MODULE.merge([a, b], tmp_path / "merged.csv", tmp_path / "report.json")
    assert report["n_merged_rows"] == 2
    assert report["n_identical_duplicates_collapsed"] == 1
    assert report["n_conflicting_keys_excluded"] == 1
    rows = list(csv.DictReader((tmp_path / "merged.csv").open()))
    assert {row["label"] for row in rows} == {"Kick", "Foley"}
