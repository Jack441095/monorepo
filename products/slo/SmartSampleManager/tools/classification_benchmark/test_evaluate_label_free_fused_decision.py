from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("evaluate_label_free_fused_decision.py")
SPEC = importlib.util.spec_from_file_location("evaluate_label_free_fused_decision", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_fused_evaluation_reports_selective_precision(tmp_path: Path):
    receipt = tmp_path / "fused.json"
    receipt.write_text(json.dumps({
        "record_type": "slo_label_free_fused_decision_receipt",
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "auto_action_allowed": False},
        "rows": [
            {"path": "/remote/sample_pack_testing/a.wav", "decision": "suggest",
             "candidate_label": "Kick", "domain": "music_sample"},
            {"path": "/remote/sample_pack_testing/b.wav", "decision": "review",
             "candidate_label": None, "domain": "music_sample"},
        ],
    }), encoding="utf-8")
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "label"])
        writer.writeheader()
        writer.writerow({"path": "/x/sample_pack_testing/a.wav", "label": "Kick"})
        writer.writerow({"path": "/x/sample_pack_testing/b.wav", "label": "Kick"})
    result = MODULE.evaluate(receipt, labels, tmp_path / "out.json")
    assert result["n_evaluated"] == 2
    assert result["overall"]["n_suggested"] == 1
    assert result["overall"]["suggestion_precision"] == 1.0
    assert result["auto_action_allowed"] is False
