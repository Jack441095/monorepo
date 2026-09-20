import csv
import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("promote_correction_review.py")
SPEC = importlib.util.spec_from_file_location("promote_correction_review", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _packet(tmp_path: Path) -> Path:
    payload = {
        "record_type": "slo_cpp_correction_review_packet",
        "safety": {"automatic_promotion": False},
        "rows": [
            {"correction_id": "corr-a", "correction_type": "label_correction", "file_path": "/x/a.wav"},
            {"correction_id": "corr-b", "correction_type": "taxonomy_gap", "file_path": "/x/b.wav"},
        ],
    }
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _decisions(tmp_path: Path, rows):
    path = tmp_path / "decisions.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODULE.DECISION_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_owner_decisions_create_candidates_but_not_training(tmp_path):
    packet = _packet(tmp_path)
    decisions = _decisions(tmp_path, [
        {"correction_id": "corr-a", "disposition": "accept", "reviewer": "jack", "reviewer_note": "heard kick"},
        {"correction_id": "corr-b", "disposition": "defer", "reviewer": "jack", "reviewer_note": "needs taxonomy review"},
    ])
    result = MODULE.promote(packet, decisions, tmp_path / "out")
    assert result["counts"] == {"accept": 1, "defer": 1, "reject": 0}
    assert result["training_ground_truth_changed"] is False
    receipt = json.loads((tmp_path / "out" / "correction_promotion_receipt.json").read_text())
    assert receipt["safety"]["automatic_promotion"] is False
    lines = (tmp_path / "out" / "correction_promotion_candidates.jsonl").read_text().splitlines()
    assert json.loads(lines[1])["promotion_status"] == "owner_approved_pending_rebuild"
    assert json.loads(lines[2])["promotion_status"] == "deferred"


def test_every_packet_row_requires_a_decision(tmp_path):
    packet = _packet(tmp_path)
    decisions = _decisions(tmp_path, [
        {"correction_id": "corr-a", "disposition": "accept", "reviewer": "jack", "reviewer_note": "ok"},
    ])
    try:
        MODULE.promote(packet, decisions, tmp_path / "out")
    except ValueError as exc:
        assert "every packet row" in str(exc)
    else:
        raise AssertionError("incomplete decision set was accepted")


def test_reject_and_defer_require_notes(tmp_path):
    packet = _packet(tmp_path)
    decisions = _decisions(tmp_path, [
        {"correction_id": "corr-a", "disposition": "reject", "reviewer": "jack", "reviewer_note": ""},
        {"correction_id": "corr-b", "disposition": "accept", "reviewer": "jack", "reviewer_note": "ok"},
    ])
    try:
        MODULE.promote(packet, decisions, tmp_path / "out")
    except ValueError as exc:
        assert "reviewer_note" in str(exc)
    else:
        raise AssertionError("note-less rejection was accepted")
