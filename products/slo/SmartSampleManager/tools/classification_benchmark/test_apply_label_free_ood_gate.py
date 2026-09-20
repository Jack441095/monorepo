from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("apply_label_free_ood_gate.py")
SPEC = importlib.util.spec_from_file_location("apply_label_free_ood_gate", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _safe(record_type: str) -> dict[str, object]:
    return {"record_type": record_type,
            "safety": {"read_only": True, "semantic_labels_created": False,
                       "rename_actions": False, "auto_action_allowed": False}}


def test_ood_gate_suppresses_high_novelty_suggestions(tmp_path: Path):
    fused = tmp_path / "fused.json"
    fused.write_text(json.dumps({**_safe("slo_label_free_fused_decision_receipt"),
        "rows": [{"path": "/a.wav", "decision": "suggest", "candidate_label": "Kick",
                  "semantic_label": None},
                 {"path": "/b.wav", "decision": "review", "candidate_label": None,
                  "semantic_label": None}]}), encoding="utf-8")
    ood = tmp_path / "ood.json"
    ood.write_text(json.dumps({**_safe("slo_label_free_embedding_ood_receipt"),
        "rows": [{"path": "/a.wav", "novelty_score": 0.5},
                 {"path": "/b.wav", "novelty_score": 0.1}]}), encoding="utf-8")
    result = MODULE.apply(fused, ood, tmp_path / "out.json", threshold=0.35)
    assert result["n_ood_overridden"] == 1
    row = result["rows"][0]
    assert row["decision"] == "review"
    assert row["suppressed_candidate_label"] == "Kick"
    assert row["candidate_label"] is None


def test_ood_gate_rejects_incomplete_join(tmp_path: Path):
    fused = tmp_path / "fused.json"
    fused.write_text(json.dumps({**_safe("slo_label_free_fused_decision_receipt"),
        "rows": [{"path": "/a.wav", "decision": "review", "semantic_label": None}]}), encoding="utf-8")
    ood = tmp_path / "ood.json"
    ood.write_text(json.dumps({**_safe("slo_label_free_embedding_ood_receipt"), "rows": []}), encoding="utf-8")
    try:
        MODULE.apply(fused, ood, tmp_path / "out.json")
    except ValueError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("incomplete OOD join was accepted")
