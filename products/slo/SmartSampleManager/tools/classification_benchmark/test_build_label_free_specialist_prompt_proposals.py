from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("build_label_free_specialist_prompt_proposals.py")
SPEC = importlib.util.spec_from_file_location("build_label_free_specialist_prompt_proposals", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_tokens_are_weak_review_descriptors(tmp_path: Path):
    source = tmp_path / "audit.json"
    source.write_text(json.dumps({
        "record_type": "slo_label_free_cluster_specialist_proposal_audit",
        "safety": {"read_only": True, "semantic_labels_created": False,
                    "rename_actions": False, "source_audio_modified": False},
        "proposals": [{"cluster_id": 2, "cluster_size": 3,
                        "proposal": "new_specialist_or_ontology_review",
                        "review_priority": 0.8, "dominant_domain": "environment_sfx",
                        "representative_paths": ["Pack/Glass_Shatter_Foley_01.wav",
                                                  "Pack/Glass_Shatter_Foley_02.wav"]}],
    }), encoding="utf-8")
    result = MODULE.build(source, tmp_path / "out.json")
    row = result["rows"][0]
    assert row["candidate_descriptors"][0]["descriptor"] == "glass"
    assert row["semantic_label"] is None
    assert result["safety"]["prompt_bank_promoted"] is False


def test_rejects_mutating_audit(tmp_path: Path):
    source = tmp_path / "audit.json"
    source.write_text(json.dumps({
        "record_type": "slo_label_free_cluster_specialist_proposal_audit",
        "safety": {"read_only": True, "semantic_labels_created": True},
        "proposals": [],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="read-only"):
        MODULE.build(source, tmp_path / "out.json")
