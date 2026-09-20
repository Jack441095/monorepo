from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("audit_label_free_cluster_specialist_proposals.py")
SPEC = importlib.util.spec_from_file_location("audit_label_free_cluster_specialist_proposals", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_audit_flags_mixed_cluster_for_router_review(tmp_path: Path):
    clusters = tmp_path / "clusters.json"
    packet = tmp_path / "packet.json"
    safe_cluster = {"read_only": True, "semantic_labels_created": False,
                    "rename_actions": False, "source_audio_modified": False}
    clusters.write_text(json.dumps({
        "record_type": "slo_label_free_cluster_manifest", "safety": safe_cluster,
        "rows": [{"path": "a.wav", "cluster_id": 1, "semantic_label": None},
                  {"path": "b.wav", "cluster_id": 1, "semantic_label": None}],
    }), encoding="utf-8")
    packet.write_text(json.dumps({
        "record_type": "slo_label_free_evidence_packet", "safety": safe_cluster,
        "rows": [
            {"path": "a.wav", "domain_route": {"domain_suggestion": "music_sample"},
             "specialist": {"specialist_suggestion": "Kick"},
             "fused_decision": {"decision": "review"}},
            {"path": "b.wav", "domain_route": {"domain_suggestion": "speech_voice"},
             "specialist": {"specialist_suggestion": "Speech"},
             "fused_decision": {"decision": "unknown_domain"}},
        ],
    }), encoding="utf-8")
    result = MODULE.audit(clusters, packet, tmp_path / "out.json")
    assert result["proposals"][0]["proposal"] == "improve_domain_router"
    assert result["proposals"][0]["semantic_label"] is None


def test_rejects_semantic_cluster_input(tmp_path: Path):
    source = tmp_path / "clusters.json"
    source.write_text(json.dumps({
        "record_type": "slo_label_free_cluster_manifest",
        "safety": {"read_only": True, "semantic_labels_created": True},
        "rows": [],
    }), encoding="utf-8")
    packet = tmp_path / "packet.json"
    packet.write_text(json.dumps({
        "record_type": "slo_label_free_evidence_packet",
        "safety": {"read_only": True, "semantic_labels_created": False},
        "rows": [],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="read-only"):
        MODULE.audit(source, packet, tmp_path / "out.json")
