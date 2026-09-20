from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("evaluate_label_free_embedding_ood.py")
SPEC = importlib.util.spec_from_file_location("evaluate_label_free_embedding_ood", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_ood_evaluation_describes_decision_slices(tmp_path: Path):
    ood = tmp_path / "ood.json"
    ood.write_text(json.dumps({
        "record_type": "slo_label_free_embedding_ood_receipt",
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "auto_action_allowed": False},
        "rows": [
            {"path": "/x/sample_pack_testing/a.wav", "novelty_score": 0.1,
             "fused_decision": "suggest"},
            {"path": "/x/sample_pack_testing/b.wav", "novelty_score": 0.5,
             "fused_decision": "review"},
        ],
    }), encoding="utf-8")
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "label"])
        writer.writeheader()
        writer.writerow({"path": "/y/sample_pack_testing/a.wav", "label": "Kick"})
        writer.writerow({"path": "/y/sample_pack_testing/b.wav", "label": "Snare"})
    result = MODULE.evaluate(ood, labels, tmp_path / "out.json")
    assert result["n_overlap"] == 2
    assert result["by_fused_decision"]["review"]["n_above_review_threshold"] == 1
    assert result["safety"]["auto_action_allowed"] is False
