import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("build_class_conditional_gate_validation_manifest.py")
SPEC = importlib.util.spec_from_file_location("slo_validation_manifest", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_load_excluded_paths_accepts_list_and_receipt(tmp_path):
    list_path = tmp_path / "list.json"
    list_path.write_text(json.dumps([{"path": "/library/a.wav"}]), encoding="utf-8")
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps({"items": [{"path": "/library/b.wav"}]}), encoding="utf-8")

    assert MODULE.load_excluded_paths(list_path) == {"/library/a.wav"}
    assert MODULE.load_excluded_paths(receipt_path) == {"/library/b.wav"}


def test_load_excluded_paths_rejects_malformed_payload(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"items": "not-an-array"}), encoding="utf-8")

    with pytest.raises(ValueError, match="items must be an array"):
        MODULE.load_excluded_paths(path)

