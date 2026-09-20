import csv
import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_explicit_approval_receipt.py")
SPEC = importlib.util.spec_from_file_location("build_explicit_approval_receipt", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fixtures(tmp_path):
    source = tmp_path / "kick.wav"
    source.write_bytes(b"audio")
    plan = tmp_path / "plan.jsonl"
    row = {"path": str(source), "destination": str(tmp_path / "Kick - kick.wav"), "signature": MODULE._signature(str(source)), "decision": {"action": "suggest"}}
    header = {"record_type": "slo_rename_plan", "n_files": 1, "source_root": str(tmp_path)}
    plan.write_text(json.dumps(header) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    guard = tmp_path / "guard.json"
    _write(guard, {"record_type": "slo_rename_duplicate_guard_audit", "source_plan_sha256": MODULE._sha256(plan), "rows": [{"path": str(source), "flags": []}]})
    collection = tmp_path / "collection.json"
    _write(collection, {"record_type": "slo_review_collections", "source_plan": str(plan), "source_plan_sha256": MODULE._sha256(plan), "collections": {"suggest": [{"path": str(source), "destination": str(tmp_path / "Kick - kick.wav"), "predicted_class": "Kick"}]}})
    decisions = tmp_path / "decisions.csv"
    with decisions.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "destination", "predicted_class", "filename_class", "confidence", "similarity", "duplicate_flags", "owner_decision", "owner_reviewer", "owner_note"])
        writer.writeheader()
        writer.writerow({"path": str(source), "destination": str(tmp_path / "Kick - kick.wav"), "predicted_class": "Kick", "filename_class": "", "confidence": "", "similarity": "", "duplicate_flags": "", "owner_decision": "approve", "owner_reviewer": "owner", "owner_note": "heard kick"})
    return collection, guard, decisions, source


def test_builds_ready_receipt_only_after_explicit_approval(tmp_path):
    collection, guard, decisions, source = _fixtures(tmp_path)
    receipt = MODULE.build_receipt(collection, guard, decisions)
    assert receipt["counts"]["ready_for_explicit_approval"] == 1
    assert receipt["safety"]["approval_granted"] is True
    assert receipt["rows"][0]["owner_reviewer"] == "owner"


def test_duplicate_flag_blocks_owner_approval(tmp_path):
    collection, guard, decisions, source = _fixtures(tmp_path)
    guard_payload = json.loads(guard.read_text())
    guard_payload["rows"][0]["flags"] = ["acoustic_near_duplicate"]
    guard.write_text(json.dumps(guard_payload), encoding="utf-8")
    receipt = MODULE.build_receipt(collection, guard, decisions)
    assert receipt["counts"]["ready_for_explicit_approval"] == 0
    assert "acoustic_near_duplicate" in receipt["rows"][0]["reasons"]


def test_evidence_edit_is_rejected(tmp_path):
    collection, guard, decisions, source = _fixtures(tmp_path)
    lines = decisions.read_text().splitlines()
    fields = lines[1].split(",")
    fields[2] = "Changed"
    lines[1] = ",".join(fields)
    decisions.write_text("\n".join(lines) + "\n")
    receipt = MODULE.build_receipt(collection, guard, decisions)
    assert receipt["counts"]["ready_for_explicit_approval"] == 0
    assert "predicted_class_changed" in receipt["rows"][0]["reasons"]
