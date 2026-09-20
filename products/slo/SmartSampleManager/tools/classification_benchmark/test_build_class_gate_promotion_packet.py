import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_class_gate_promotion_packet.py")
SPEC = importlib.util.spec_from_file_location("build_class_gate_promotion_packet", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _write_inputs(tmp_path, complete=True):
    queue = tmp_path / "queue.json"
    queue.write_text(json.dumps({
        "record_type": "slo_class_conditional_gate_testing_review",
        "rows": [
            {"candidate_class": "Kick"}, {"candidate_class": "Snare"},
        ],
    }), encoding="utf-8")
    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps({
        "record_type": "slo_class_conditional_gate_validation",
        "summary": {"n_manifest": 80 if complete else 79, "n_labelled": 80},
        "classes": {
            "Kick": {"n": 40, "correct": 39, "precision": .975, "descriptive_95": True},
            "Snare": {"n": 40, "correct": 30, "precision": .75, "descriptive_95": False},
        },
    }), encoding="utf-8")
    return queue, validation


def test_packet_marks_only_descriptive_classes_for_explicit_review(tmp_path):
    queue, validation = _write_inputs(tmp_path)
    packet = MODULE.build_packet(queue, validation)
    assert packet["summary"] == {"n_candidates": 2, "candidate_classes": 2, "review_approval_candidate_classes": 1}
    assert packet["classes"]["Kick"]["review_approval_candidate"] is True
    assert packet["classes"]["Snare"]["review_approval_candidate"] is False
    assert packet["safety"]["auto_approved"] is False


def test_packet_fails_closed_on_incomplete_validation(tmp_path):
    queue, validation = _write_inputs(tmp_path, complete=False)
    try:
        MODULE.build_packet(queue, validation)
    except ValueError as exc:
        assert "incomplete" in str(exc)
    else:
        raise AssertionError("incomplete validation was accepted")
