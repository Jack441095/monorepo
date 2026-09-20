from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("taxonomy_gap_review_tool.py")
SPEC = importlib.util.spec_from_file_location("slo_taxonomy_gap_review_tool", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _queue(path: Path, audio: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.FIELDS)
        writer.writeheader()
        writer.writerow({
            "batch_row": "1", "id": "1", "path": str(audio),
            "content_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
            "observed_label": "Synth One-Shot",
            "candidate_parent_options": "Synth|OOD", "collection": "C",
            "pack": "P", "sample_family_id": "F", "label_source": "review",
            "owner_label": "", "owner_note": "", "owner_reviewer": "",
            "decision_status": "pending",
        })


def test_review_state_requires_note_and_restricts_options(tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"audio")
    queue = tmp_path / "queue.csv"; _queue(queue, audio)
    state = MODULE.ReviewState(MODULE.load_queue(queue), tmp_path / "out.csv", "owner")
    with pytest.raises(ValueError, match="note"):
        state.record("1", "Synth", "")
    with pytest.raises(ValueError, match="not an option"):
        state.record("1", "Kick", "heard kick")
    state.record("1", "Synth", "heard a sustained synth tone")
    with (tmp_path / "out.csv").open(newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["owner_label"] == "Synth" and row["owner_reviewer"] == "owner"
    assert state.next_item() is None


def test_unknown_is_normalized_to_ood(tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"audio")
    queue = tmp_path / "queue.csv"; _queue(queue, audio)
    state = MODULE.ReviewState(MODULE.load_queue(queue), tmp_path / "out.csv", "owner")
    state.record("1", "UNKNOWN", "not enough evidence for a supported class")
    with (tmp_path / "out.csv").open(newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["owner_label"] == "OOD" and row["decision_status"] == "approved"


def test_queue_hash_mismatch_is_rejected(tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"audio")
    queue = tmp_path / "queue.csv"; _queue(queue, audio)
    text = queue.read_text().replace(hashlib.sha256(b"audio").hexdigest(), "0" * 64)
    queue.write_text(text)
    with pytest.raises(ValueError, match="hash mismatch"):
        MODULE.load_queue(queue)


def test_malformed_resume_row_is_rejected(tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"audio")
    queue = tmp_path / "queue.csv"; _queue(queue, audio)
    output = tmp_path / "out.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.FIELDS); writer.writeheader()
        row = {field: "" for field in MODULE.FIELDS}
        row.update({"id": "1", "path": str(audio),
                    "content_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
                    "owner_label": "Synth", "decision_status": "pending"})
        writer.writerow(row)
    with pytest.raises(ValueError, match="incomplete"):
        MODULE.ReviewState(MODULE.load_queue(queue), output, "owner")


def test_cli_refuses_to_overwrite_source_queue(tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"audio")
    queue = tmp_path / "queue.csv"; _queue(queue, audio)
    with pytest.raises(ValueError, match="different from the source queue"):
        MODULE.main(["--queue", str(queue), "--out", str(queue), "--reviewer", "owner"])


def test_cli_refuses_hardlink_to_source_queue(tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"audio")
    queue = tmp_path / "queue.csv"; _queue(queue, audio)
    hardlink = tmp_path / "queue_copy.csv"; hardlink.hardlink_to(queue)
    with pytest.raises(ValueError, match="different from the source queue"):
        MODULE.main(["--queue", str(queue), "--out", str(hardlink), "--reviewer", "owner"])


def test_evidence_loader_is_review_only_and_hash_keyed(tmp_path: Path):
    content_hash = "a" * 64
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({
        "record_type": "slo_taxonomy_gap_ai_option_filtered_receipt",
        "safety": {"read_only": True, "semantic_labels_created": False,
                    "owner_labels_created": False, "rename_actions": False},
        "rows": [{"content_sha256": content_hash, "ai_candidate_label": "Synth",
                  "ai_candidate_score": 0.4, "ai_candidate_margin": 0.1,
                  "ai_allowed_alternatives": [], "semantic_label": None}],
    }))
    loaded = MODULE.load_evidence(evidence)
    assert loaded[content_hash]["label"] == "Synth"


def test_evidence_loader_rejects_semantic_label(tmp_path: Path):
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({
        "record_type": "slo_taxonomy_gap_ai_option_filtered_receipt",
        "safety": {"read_only": True},
        "rows": [{"content_sha256": "a" * 64, "semantic_label": "Synth"}],
    }))
    with pytest.raises(ValueError, match="semantic label"):
        MODULE.load_evidence(evidence)
