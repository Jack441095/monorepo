from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("evaluate_label_free_retrieval_evidence.py")
SPEC = importlib.util.spec_from_file_location("evaluate_label_free_retrieval_evidence", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_rejects_mutating_receipt(tmp_path: Path):
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({
        "record_type": "slo_label_free_retrieval_evidence",
        "safety": {"read_only": True, "semantic_labels_created": True}, "rows": [],
    }), encoding="utf-8")
    labels = tmp_path / "labels.csv"
    labels.write_text("path,label\na.wav,Kick\n", encoding="utf-8")
    with pytest.raises(ValueError, match="read-only"):
        MODULE.evaluate(receipt, labels, tmp_path / "out.json")
