from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("build_label_free_physical_cards.py")
SPEC = importlib.util.spec_from_file_location("build_label_free_physical_cards", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _queue(path: Path) -> Path:
    payload = {
        "record_type": "slo_label_free_review_queue", "method_version": "test",
        "safety": {"read_only": True, "semantic_labels_created": False, "rename_actions": False},
        "rows": [{"path": "/tmp/a.wav"}, {"path": "/tmp/b.wav"}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_writes_physical_only_cards_and_errors(tmp_path, monkeypatch):
    def fake(path):
        logical, analysis = path
        if logical.endswith("b.wav"):
            return None, {"path": logical, "analysis_path": analysis, "error": "decode"}
        return {"record_type": "slo_audio_definition_card", "path": logical,
                "analysis_path": analysis, "semantic_label": None, "heuristic_tags": ["bright"]}, None
    monkeypatch.setattr(MODULE, "_analyse", fake)
    payload = MODULE.build(_queue(tmp_path / "queue.json"), tmp_path / "cards.json", limit=2)
    assert payload["n_requested"] == 2
    assert payload["n_cards"] == 1
    assert payload["n_errors"] == 1
    assert payload["safety"]["read_only"]
    assert payload["safety"]["semantic_labels_created"] is False


def test_build_rejects_non_queue(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"record_type": "other"}), encoding="utf-8")
    with pytest.raises(ValueError, match="review queue"):
        MODULE.build(path, tmp_path / "out.json")
