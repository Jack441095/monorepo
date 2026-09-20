from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("label_free_specialist_classifier.py")
SPEC = importlib.util.spec_from_file_location("label_free_specialist_classifier", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_prompt_bank_contains_specialists_for_open_world_routes():
    bank = MODULE._load_bank(MODULE.DEFAULT_BANK)
    assert {"music_sample", "speech_voice", "environment_sfx", "animal_bioacoustic",
            "mechanical_industrial", "ambience_field"} <= set(bank)
    assert all(labels and all(prompts for prompts in labels.values()) for labels in bank.values())


def test_router_reader_rejects_semantic_labels(tmp_path: Path):
    path = tmp_path / "router.jsonl"
    header = {
        "record_type": "slo_label_free_domain_router_receipt",
        "safety": {"read_only": True, "semantic_labels_created": False, "rename_actions": False},
    }
    row = {"path": "/tmp/a.wav", "domain_suggestion": "music_sample", "semantic_label": "Kick"}
    path.write_text(json.dumps(header) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="semantic labels"):
        MODULE._read_router(path)


def test_undispatched_rows_are_review_only():
    row = MODULE._undispatched("/tmp/a.wav", "unknown_or_mixture", "route is unknown or abstained")
    assert row["status"] == "review"
    assert row["specialist_status"] == "not_dispatched"
    assert row["semantic_label"] is None
