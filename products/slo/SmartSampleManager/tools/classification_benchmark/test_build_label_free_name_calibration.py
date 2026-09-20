from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_label_free_name_calibration.py")
SPEC = importlib.util.spec_from_file_location("build_label_free_name_calibration", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _packet(path: Path, source: str) -> None:
    rows = []
    for name, domain in (("a.wav", "music_sample"), ("b.wav", "music_sample"),
                         ("c.wav", "environment_sfx")):
        rows.append({
            "path": str((path / name).resolve()), "semantic_label": None,
            "review_state": "suggestion_review_required",
            "domain_route": {"domain_suggestion": domain, "semantic_label": None},
            "name_candidate": {"candidate_filename": f"{name[:-4]}_one-shot.wav",
                                "name_state": "suggested_review_required",
                                "semantic_label": None},
        })
    packet = {"record_type": "slo_label_free_evidence_packet", "rows": rows,
              "coverage": {"name_candidate": len(rows)},
              "safety": {"read_only": True, "semantic_labels_created": False,
                         "rename_actions": False, "source_audio_modified": False}}
    source.write_text(json.dumps(packet), encoding="utf-8")


def _append(log: Path, packet_file: Path, file_name: str, event_type: str) -> None:
    feedback = MODULE._load_feedback_module()
    path = str((packet_file.parent / file_name).resolve())
    expected = f"{file_name[:-4]}_one-shot.wav"
    feedback.append_event(log, {
        "event_id": f"evt-{file_name}", "event_type": event_type, "path": path,
        "actor": "tester", "created_at": "2026-09-13T00:00:00Z",
        "source_plan_sha256": "a" * 64, "previous_decision": "review",
        "source_packet_sha256": hashlib.sha256(packet_file.read_bytes()).hexdigest(),
        "candidate_filename": expected,
        **({"corrected_filename": "corrected_one-shot.wav"}
           if event_type == "correct_name_candidate" else {}),
        **({"note": "wrong candidate"} if event_type == "reject_name_candidate" else {}),
    })


def test_calibration_uses_latest_decision_and_wilson_gate(tmp_path: Path):
    packet_path = tmp_path / "packet.json"
    _packet(tmp_path, packet_path)
    feedback = tmp_path / "feedback.jsonl"
    _append(feedback, packet_path, "a.wav", "accept_name_candidate")
    _append(feedback, packet_path, "b.wav", "correct_name_candidate")
    _append(feedback, packet_path, "c.wav", "reject_name_candidate")
    result = MODULE.build(packet_path, feedback, tmp_path / "report.json", min_reviews=1)
    assert result["n_name_events"] == 3
    assert result["n_adjudicated_paths"] == 3
    assert result["slices"]["music_sample"]["n_accepted"] == 1
    assert result["slices"]["music_sample"]["n_rejected_or_corrected"] == 1
    assert result["auto_action_allowed"] is False
    assert result["safety"]["automatic_promotion"] is False


def test_calibration_rejects_feedback_for_wrong_candidate(tmp_path: Path):
    packet_path = tmp_path / "packet.json"
    _packet(tmp_path, packet_path)
    feedback = tmp_path / "feedback.jsonl"
    feedback.write_text(json.dumps({
        "event_id": "evt-bad", "event_type": "accept_name_candidate",
        "path": str((tmp_path / "a.wav").resolve()), "actor": "tester",
        "created_at": "2026-09-13T00:00:00Z", "source_plan_sha256": "a" * 64,
        "previous_decision": "review", "candidate_filename": "other.wav",
        "source_packet_sha256": hashlib.sha256(packet_path.read_bytes()).hexdigest(),
    }) + "\n", encoding="utf-8")
    try:
        MODULE.build(packet_path, feedback, tmp_path / "report.json")
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("mismatched candidate feedback was accepted")


def test_calibration_rejects_feedback_from_another_packet(tmp_path: Path):
    packet_path = tmp_path / "packet.json"
    _packet(tmp_path, packet_path)
    feedback = tmp_path / "feedback.jsonl"
    feedback.write_text(json.dumps({
        "event_id": "evt-stale", "event_type": "accept_name_candidate",
        "path": str((tmp_path / "a.wav").resolve()), "actor": "tester",
        "created_at": "2026-09-13T00:00:00Z", "source_plan_sha256": "a" * 64,
        "source_packet_sha256": "b" * 64, "previous_decision": "review",
        "candidate_filename": "a_one-shot.wav",
    }) + "\n", encoding="utf-8")
    try:
        MODULE.build(packet_path, feedback, tmp_path / "report.json")
    except ValueError as exc:
        assert "packet hash" in str(exc)
    else:
        raise AssertionError("stale packet feedback was accepted")
