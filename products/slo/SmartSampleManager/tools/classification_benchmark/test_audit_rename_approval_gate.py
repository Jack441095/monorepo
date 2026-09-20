import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("audit_rename_approval_gate.py")
SPEC = importlib.util.spec_from_file_location("audit_rename_approval_gate", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_suggestion_is_blocked_without_approval(tmp_path):
    source = tmp_path / "sound.wav"
    source.write_bytes(b"audio")
    signature = MODULE._signature(str(source))
    plan = tmp_path / "plan.jsonl"
    _write_jsonl(plan, [{"record_type": "slo_rename_plan", "n_files": 1, "source_root": str(tmp_path), "qualified_classes": []},
                       {"path": str(source), "destination": str(tmp_path / "Kick - sound.wav"), "audio_class": "Kick", "decision": {"action": "suggest"}, "approved": False, "signature": signature}])
    guard = tmp_path / "guard.json"
    guard.write_text(json.dumps({"rows": [{"path": str(source), "flags": []}]}), encoding="utf-8")
    result = MODULE.audit(plan, guard)
    assert result["counts"]["blocked"] == 1
    assert result["counts"]["suggestion_requires_explicit_approval"] == 1
    assert result["safety"]["approval_granted"] is False


def test_auto_row_with_qualified_class_can_be_ready(tmp_path):
    source = tmp_path / "sound.wav"
    source.write_bytes(b"audio")
    signature = MODULE._signature(str(source))
    plan = tmp_path / "plan.jsonl"
    _write_jsonl(plan, [{"record_type": "slo_rename_plan", "n_files": 1, "source_root": str(tmp_path), "qualified_classes": ["Kick"]},
                       {"path": str(source), "destination": str(tmp_path / "Kick - sound.wav"), "audio_class": "Kick", "decision": {"action": "auto_rename"}, "approved": False, "signature": signature}])
    guard = tmp_path / "guard.json"
    guard.write_text(json.dumps({"rows": [{"path": str(source), "flags": []}]}), encoding="utf-8")
    result = MODULE.audit(plan, guard)
    assert result["counts"]["ready_for_explicit_approval"] == 1


def test_duplicate_flags_are_separated_from_approval_blockers(tmp_path):
    source = tmp_path / "sound.wav"
    source.write_bytes(b"audio")
    signature = MODULE._signature(str(source))
    plan = tmp_path / "plan.jsonl"
    _write_jsonl(plan, [{"record_type": "slo_rename_plan", "n_files": 1, "source_root": str(tmp_path), "qualified_classes": []},
                       {"path": str(source), "destination": str(tmp_path / "Kick - sound.wav"), "audio_class": "Kick", "decision": {"action": "suggest"}, "approved": False, "signature": signature}])
    guard = tmp_path / "guard.json"
    guard.write_text(json.dumps({"rows": [{"path": str(source), "flags": ["exact_duplicate_alias"]}]}), encoding="utf-8")
    result = MODULE.audit(plan, guard)
    assert result["qualification_summary"] == {
        "suggestion_rows": 1,
        "duplicate_blocked_rows": 1,
        "suggestion_rows_without_duplicate_flags": 0,
        "ready_for_explicit_approval": 0,
    }
