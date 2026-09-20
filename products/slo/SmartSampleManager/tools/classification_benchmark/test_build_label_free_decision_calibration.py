from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_label_free_decision_calibration.py")
SPEC = importlib.util.spec_from_file_location("build_label_free_decision_calibration", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _feedback_module():
    path = Path(__file__).with_name("review_feedback_events.py")
    spec = importlib.util.spec_from_file_location("review_feedback_events_fixture", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_decision_calibration_joins_packet_hash_and_never_promotes(tmp_path: Path):
    source = str((tmp_path / "sample.wav").resolve())
    packet = tmp_path / "packet.json"
    packet.write_text(json.dumps({
        "record_type": "slo_label_free_evidence_packet",
        "rows": [{"path": source, "semantic_label": None,
                  "fused_decision": {"candidate_label": "Kick", "domain_candidate_label": None,
                                      "candidate_scope": "music_taxonomy", "domain": "music_sample"}}],
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "source_audio_modified": False},
    }), encoding="utf-8")
    packet_hash = hashlib.sha256(packet.read_bytes()).hexdigest()
    feedback = tmp_path / "feedback.jsonl"
    module = _feedback_module()
    module.append_event(feedback, {
        "event_id": "evt-1", "event_type": "accept_fused_candidate", "path": source,
        "actor": "reviewer", "created_at": "2026-09-14T00:00:00Z",
        "source_plan_sha256": "a" * 64, "source_packet_sha256": packet_hash,
        "previous_decision": "suggest", "candidate_label": "Kick",
    })
    result = MODULE.build(packet, feedback, tmp_path / "out.json", min_reviews=1)
    assert result["n_adjudicated_paths"] == 1
    assert result["slices"]["all"]["observed_precision"] == 1.0
    assert result["promotion_candidate_slices"] == []
    assert result["auto_action_allowed"] is False
