import json
from pathlib import Path

import pytest

from build_label_free_ensemble_receipt import combine


def _receipt(path: Path, model: str, rows: list[dict]):
    header = {
        "record_type": "slo_label_free_zero_shot_receipt",
        "prompt_bank": {"Kick": ["a kick drum"]},
        "model": model,
        "views": 3,
        "safety": {"read_only": True, "semantic_labels_created": False, "rename_actions": False},
    }
    path.write_text("\n".join([json.dumps(header)] + [json.dumps(r) for r in rows]) + "\n", encoding="utf-8")


def _row(path: str, label: str, status: str = "suggest"):
    return {"path": path, "content_sha256": "abc", "status": status,
            "semantic_label": None, "zero_shot_suggestion": label,
            "semantic_score": 0.3, "margin": 0.1,
            "alternatives": [{"label": label, "score": 0.3}]}


def test_agreement_keeps_suggest_and_disagreement_abstains(tmp_path: Path):
    a, b, out = (tmp_path / x for x in ("a.jsonl", "b.jsonl", "out.jsonl"))
    _receipt(a, "a", [_row("x.wav", "Kick"), _row("y.wav", "Kick")])
    _receipt(b, "b", [_row("x.wav", "Kick"), _row("y.wav", "Snare")])
    header = combine(a, b, out)
    rows = [json.loads(x) for x in out.read_text().splitlines()[1:]]
    assert header["n_suggest"] == 1
    assert rows[0]["status"] == "suggest"
    assert rows[1]["status"] == "review"
    assert rows[1]["ensemble_suggestion"] is None


def test_combiner_fails_on_coverage_mismatch(tmp_path: Path):
    a, b, out = (tmp_path / x for x in ("a.jsonl", "b.jsonl", "out.jsonl"))
    _receipt(a, "a", [_row("x.wav", "Kick")])
    _receipt(b, "b", [_row("y.wav", "Kick")])
    with pytest.raises(ValueError, match="same paths"):
        combine(a, b, out)
