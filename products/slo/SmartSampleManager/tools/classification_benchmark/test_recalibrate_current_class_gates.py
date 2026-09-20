import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("recalibrate_current_class_gates.py")
SPEC = importlib.util.spec_from_file_location("slo_recalibrate_current_class_gates", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_validation_receipt_normalization_keeps_negative_label(tmp_path):
    receipt = tmp_path / "validation.json"
    receipt.write_text(json.dumps({
        "record_type": "slo_class_conditional_gate_validation",
        "rows": [
            {"path": "/library/a.wav", "candidate_class": "Clap",
             "human_label": "Clap", "vendor": "Pack A"},
            {"path": "/library/b.wav", "candidate_class": "Clap",
             "human_label": "Vocal One-Shot", "vendor": "Pack B"},
        ],
    }), encoding="utf-8")

    rows, validation_mode = MODULE.load_rows(receipt)

    assert validation_mode is True
    assert [row["label"] for row in rows] == ["Clap", "Vocal One-Shot"]
    assert [row["candidate_class"] for row in rows] == ["Clap", "Clap"]


def test_plain_manifest_requires_label_and_vendor(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"rows": [{"path": "/library/a.wav"}]}), encoding="utf-8")

    with pytest.raises(ValueError, match="path, label, or vendor"):
        MODULE.load_rows(manifest)

