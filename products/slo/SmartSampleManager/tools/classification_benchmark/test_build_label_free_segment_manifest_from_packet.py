from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_label_free_segment_manifest_from_packet.py")
SPEC = importlib.util.spec_from_file_location("build_label_free_segment_manifest_from_packet", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_packet_manifest_is_read_only_and_reports_decode_errors(tmp_path: Path):
    packet = tmp_path / "packet.json"
    packet.write_text(json.dumps({
        "record_type": "slo_label_free_evidence_packet",
        "rows": [{"path": "/missing/sample.wav", "semantic_label": None}],
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "source_audio_modified": False},
    }), encoding="utf-8")
    result = MODULE.build(packet, tmp_path / "manifest.json")
    assert result["n_requested"] == 1
    assert result["n_segmented"] == 0
    assert result["n_errors"] == 1
    assert result["safety"]["windows_are_not_semantic_labels"] is True


def test_packet_manifest_limit_is_deterministic(tmp_path: Path):
    packet = tmp_path / "packet.json"
    packet.write_text(json.dumps({
        "record_type": "slo_label_free_evidence_packet",
        "rows": [{"path": f"/missing/{i}.wav", "semantic_label": None} for i in range(3)],
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "source_audio_modified": False},
    }), encoding="utf-8")
    result = MODULE.build(packet, tmp_path / "manifest.json", limit=2)
    assert result["n_requested"] == 2
