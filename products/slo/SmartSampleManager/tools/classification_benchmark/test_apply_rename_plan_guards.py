import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("apply_rename_plan.py")
SPEC = importlib.util.spec_from_file_location("apply_rename_plan", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _plan(tmp_path, action="auto_rename"):
    source = tmp_path / "sound.wav"
    destination = tmp_path / "Kick - sound.wav"
    source.write_bytes(b"audio")
    row = {"path": str(source), "destination": str(destination), "decision": {"action": action}, "signature": MODULE.signature(str(source))}
    plan = tmp_path / "plan.jsonl"
    header = {"record_type": "slo_rename_plan", "n_files": 1, "source_root": str(tmp_path)}
    plan.write_text(json.dumps(header) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    return plan, source, row


def test_validate_blocks_duplicate_flags(tmp_path):
    plan, source, row = _plan(tmp_path)
    problems = MODULE.validate({"source_root": str(tmp_path)}, [row], False, {str(source): {"flags": ["exact_duplicate_alias"]}})
    assert any("duplicate guard flags" in problem for problem in problems)


def test_validate_allows_clean_read_only_candidate(tmp_path):
    plan, source, row = _plan(tmp_path)
    problems = MODULE.validate({"source_root": str(tmp_path)}, [row], False, {str(source): {"flags": []}})
    assert problems == []


def test_approval_gate_must_mark_auto_row_ready(tmp_path):
    plan, source, row = _plan(tmp_path)
    blocked = {str(source): {"status": "blocked", "reasons": ["class_not_qualified_for_auto_action"]}}
    assert MODULE.validate_approval_gate([row], blocked)
    ready = {str(source): {"status": "ready_for_explicit_approval", "reasons": []}}
    assert MODULE.validate_approval_gate([row], ready) == []


def test_approval_gate_also_covers_selected_suggestion(tmp_path):
    plan, source, row = _plan(tmp_path, action="suggest")
    blocked = {str(source): {"status": "blocked", "reasons": ["suggestion_requires_explicit_approval"]}}
    assert MODULE.validate_approval_gate([row], blocked, include_suggest=True)
    ready = {str(source): {"status": "ready_for_explicit_approval", "reasons": []}}
    assert MODULE.validate_approval_gate([row], ready, include_suggest=True) == []


def test_approval_gate_rejects_a_different_plan(tmp_path):
    plan, source, row = _plan(tmp_path)
    gate = tmp_path / "approval.json"
    gate.write_text(json.dumps({
        "record_type": "slo_rename_approval_gate_audit",
        "source_plan_sha256": "wrong",
        "rows": [],
    }), encoding="utf-8")
    try:
        MODULE.read_approval_gate(str(gate), str(plan))
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("mismatched approval gate was accepted")


def test_synthetic_canary_apply_and_undo_round_trip(tmp_path):
    plan, source, row = _plan(tmp_path)
    journal = tmp_path / "journal.csv"
    assert MODULE.apply([row], False, str(journal)) == 1
    destination = tmp_path / "Kick - sound.wav"
    assert not source.exists() and destination.exists()

    undo_path = Path(__file__).parents[1] / "undo_slo_sort.py"
    spec = importlib.util.spec_from_file_location("undo_slo_sort", undo_path)
    undo = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(undo)
    assert undo.main([str(journal)]) == 0
    assert undo.main([str(journal), "--apply"]) == 0
    assert source.exists() and not destination.exists()
