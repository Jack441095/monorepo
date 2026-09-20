from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("build_ground_truth_research_manifest.py")
SPEC = importlib.util.spec_from_file_location("slo_build_ground_truth_research_manifest", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


FIELDS = ["path", "label", "collection", "pack", "sample_family_id",
          "content_sha256", "label_source", "labelling_session",
          "is_impulse_response", "rejection_reason", "note"]


def _labels(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _row(audio: Path, label: str) -> dict[str, str]:
    return {field: {"path": str(audio), "label": label,
                    "collection": "Vendor A", "pack": "Pack 1",
                    "sample_family_id": "family-1", "label_source": "test",
                    "labelling_session": "reviewer-1",
                    "is_impulse_response": "false"}.get(field, "")
            for field in FIELDS}


def test_builder_preserves_reviewed_labels_and_marks_rejection_as_ood(tmp_path: Path):
    first = tmp_path / "kick.wav"; first.write_bytes(b"kick")
    reject = tmp_path / "other.wav"; reject.write_bytes(b"other")
    excluded = tmp_path / "bass.wav"; excluded.write_bytes(b"bass")
    labels = tmp_path / "labels.csv"
    rows = [_row(first, "Kick"), _row(reject, "Other/none"), _row(excluded, "Bass Hit")]
    rows[1]["rejection_reason"] = "unsupported instrument"
    _labels(labels, rows)

    manifest, receipt = MODULE.build_manifest(labels)

    assert [row["expected_subcategory"] for row in manifest] == ["Kick", "OOD"]
    assert manifest[1]["ood"] is True
    assert len(manifest[0]["sha256"]) == 64
    assert receipt["excluded_label_counts"] == {"Bass Hit": 1}
    assert receipt["policy"]["labels_invented"] is False


def test_builder_rejects_conflicting_duplicate_paths(tmp_path: Path):
    audio = tmp_path / "same.wav"; audio.write_bytes(b"same")
    labels = tmp_path / "labels.csv"
    _labels(labels, [_row(audio, "Kick"), _row(audio, "Snare")])
    with pytest.raises(ValueError, match="conflicting reviewed labels"):
        MODULE.build_manifest(labels)
