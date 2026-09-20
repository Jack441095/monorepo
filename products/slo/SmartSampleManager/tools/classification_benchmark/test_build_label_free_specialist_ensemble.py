from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_label_free_specialist_ensemble.py")
SPEC = importlib.util.spec_from_file_location("build_label_free_specialist_ensemble", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _receipt(path: Path, model: str, label: str, status: str = "suggest") -> None:
    header = {"record_type": "slo_label_free_specialist_receipt", "model": model,
              "safety": {"read_only": True, "semantic_labels_created": False, "rename_actions": False}}
    row = {"path": "/library/a.wav", "domain_suggestion": "speech_voice",
           "specialist_status": "scored", "status": status, "semantic_label": None,
           "specialist_suggestion": label, "specialist_score": 0.4,
           "specialist_alternatives": [{"label": label, "score": 0.4}],
           "view_agreement": 1.0}
    path.write_text(json.dumps(header) + "\n" + json.dumps(row) + "\n", encoding="utf-8")


def test_build_accepts_only_agreeing_passing_specialists(tmp_path: Path):
    a, b, out = tmp_path / "a.jsonl", tmp_path / "b.jsonl", tmp_path / "out.jsonl"
    _receipt(a, "model-a", "Speech")
    _receipt(b, "model-b", "Speech")
    result = MODULE.build(a, b, out)
    assert result["n_suggest"] == 1
    assert result["n_agree"] == 1
    row = json.loads(out.read_text(encoding="utf-8").splitlines()[1])
    assert row["specialist_suggestion"] == "Speech"
    assert row["semantic_label"] is None


def test_disagreement_stays_review(tmp_path: Path):
    a, b, out = tmp_path / "a.jsonl", tmp_path / "b.jsonl", tmp_path / "out.jsonl"
    _receipt(a, "model-a", "Speech")
    _receipt(b, "model-b", "Singing")
    MODULE.build(a, b, out)
    row = json.loads(out.read_text(encoding="utf-8").splitlines()[1])
    assert row["status"] == "review"
    assert row["specialist_suggestion"] is None
