from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_taxonomy_gap_coverage_plan.py")
SPEC = importlib.util.spec_from_file_location("slo_taxonomy_gap_coverage", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_plan_reports_family_deficits_and_candidates(tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"audio")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([
        {"expected_subcategory": "Kick", "ood": False, "source_family": "A", "vendor_id": "V"},
        {"expected_subcategory": "OOD", "ood": True, "source_family": "X", "vendor_id": "O"},
    ]))
    queue = tmp_path / "queue.csv"
    fields = ["id", "candidate_parent_options", "collection", "sample_family_id",
              "owner_label", "decision_status"]
    with queue.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        writer.writerow({"id": "1", "candidate_parent_options": "Synth|OOD",
                         "collection": "C", "sample_family_id": "S1",
                         "owner_label": "", "decision_status": "pending"})
    result = MODULE.build_plan(manifest, queue)
    assert result["classes"]["Synth"]["candidate_rows_offering_class"] == 1
    assert result["classes"]["Synth"]["new_source_families_available"] == 1
    assert result["classes"]["Synth"]["max_assignable_new_families"] == 1
    assert result["classes"]["Synth"]["gate_feasible_under_owner_assignment"] is False
    assert result["policy"]["candidate_options_are_not_labels"] is True


def test_plan_hashes_inputs(tmp_path: Path):
    manifest = tmp_path / "manifest.json"; manifest.write_text("[]")
    queue = tmp_path / "queue.csv"; queue.write_text("id,candidate_parent_options,collection,sample_family_id,owner_label,decision_status\n")
    result = MODULE.build_plan(manifest, queue)
    assert result["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert result["queue_sha256"] == hashlib.sha256(queue.read_bytes()).hexdigest()


def test_completed_owner_row_counts_as_evidence_not_a_candidate(tmp_path: Path):
    manifest = tmp_path / "manifest.json"; manifest.write_text("[]")
    queue = tmp_path / "queue.csv"
    fields = ["id", "candidate_parent_options", "collection", "sample_family_id",
              "owner_label", "decision_status"]
    with queue.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        writer.writerow({"id": "1", "candidate_parent_options": "Synth|OOD",
                         "collection": "C", "sample_family_id": "S1",
                         "owner_label": "Synth", "decision_status": "approved"})
    result = MODULE.build_plan(manifest, queue)
    assert result["completed_owner_rows"] == 1
    assert result["pending_owner_rows"] == 0
    assert result["classes"]["Synth"]["known_rows"] == 1
    assert result["classes"]["Synth"]["candidate_rows_offering_class"] == 0
