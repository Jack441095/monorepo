from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("filter_taxonomy_gap_ai_suggestions.py")
SPEC = importlib.util.spec_from_file_location("slo_filter_gap_ai", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_filter_keeps_only_offered_options(tmp_path: Path):
    audio = tmp_path / "a.wav"; audio.write_bytes(b"audio")
    queue = tmp_path / "queue.csv"
    fields = ["id", "path", "content_sha256", "candidate_parent_options"]
    with queue.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        writer.writerow({"id": "1", "path": str(audio),
                         "content_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
                         "candidate_parent_options": "Synth|OOD"})
    receipt = tmp_path / "receipt.jsonl"
    h = {"record_type": "slo_label_free_zero_shot_receipt", "safety": {"read_only": True}}
    row = {"path": str(audio), "content_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
           "zero_shot_suggestion": "Kick", "status": "suggest", "alternatives": [
               {"label": "Kick", "score": 0.9}, {"label": "Synth", "score": 0.4},
               {"label": "OOD", "score": 0.2}]}
    receipt.write_text(json.dumps(h) + "\n" + json.dumps(row) + "\n")
    out = tmp_path / "out.json"
    result = MODULE.filter_suggestions(queue, receipt, out)
    payload = json.loads(out.read_text())
    assert result["n_ai_candidate_rows"] == 1
    assert payload["rows"][0]["ai_candidate_label"] == "Synth"
    assert payload["rows"][0]["semantic_label"] is None


def test_filter_rejects_coverage_gap(tmp_path: Path):
    queue = tmp_path / "queue.csv"; queue.write_text("id,path,content_sha256,candidate_parent_options\n1,/tmp/a.wav," + "0" * 64 + ",Synth|OOD\n")
    receipt = tmp_path / "receipt.jsonl"; receipt.write_text(json.dumps({"record_type": "slo_label_free_zero_shot_receipt", "safety": {"read_only": True}}) + "\n")
    with pytest.raises(ValueError, match="coverage mismatch"):
        MODULE.filter_suggestions(queue, receipt, tmp_path / "out.json")


def test_filter_refuses_to_alias_queue(tmp_path: Path):
    audio = tmp_path / "a.wav"; audio.write_bytes(b"audio")
    queue = tmp_path / "queue.csv"
    queue.write_text("id,path,content_sha256,candidate_parent_options\n1," + str(audio) + "," + hashlib.sha256(audio.read_bytes()).hexdigest() + ",Synth|OOD\n")
    receipt = tmp_path / "receipt.jsonl"
    receipt.write_text(json.dumps({"record_type": "slo_label_free_zero_shot_receipt", "safety": {"read_only": True}}) + "\n")
    with pytest.raises(ValueError, match="different from its inputs"):
        MODULE.filter_suggestions(queue, receipt, queue)
