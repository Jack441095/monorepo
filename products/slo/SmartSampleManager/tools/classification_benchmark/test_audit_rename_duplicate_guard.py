import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("audit_rename_duplicate_guard.py")
SPEC = importlib.util.spec_from_file_location("audit_rename_duplicate_guard", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_flags_exact_alias_and_near_group_without_mutating_plan(tmp_path):
    canonical = str((tmp_path / "a.wav").resolve())
    alias = str((tmp_path / "b.wav").resolve())
    near = str((tmp_path / "c.wav").resolve())
    plan = tmp_path / "plan.jsonl"
    _write_jsonl(plan, [
        {"record_type": "slo_rename_plan"},
        {"path": alias, "decision": {"action": "suggest"}},
        {"path": near, "decision": {"action": "review"}},
    ])
    exact = tmp_path / "exact.json"
    exact.write_text(json.dumps({"groups": [{"canonical_path": canonical, "alias_paths": [alias]}]}), encoding="utf-8")
    near_file = tmp_path / "near.json"
    near_file.write_text(json.dumps({"groups": [{"member_paths": [near, canonical]}]}), encoding="utf-8")
    before = plan.read_bytes()
    result = MODULE.audit(plan, exact, near_file)
    assert result["flag_counts"]["exact_duplicate_alias"] == 1
    assert result["flag_counts"]["acoustic_near_duplicate"] == 1
    assert result["safety"]["rename_plan_modified"] is False
    assert plan.read_bytes() == before


def test_auto_exact_duplicate_is_counted_as_violation(tmp_path):
    path = str((tmp_path / "a.wav").resolve())
    plan = tmp_path / "plan.jsonl"
    _write_jsonl(plan, [{"record_type": "slo_rename_plan"}, {"path": path, "decision": {"action": "auto_rename"}}])
    exact = tmp_path / "exact.json"
    exact.write_text(json.dumps({"groups": [{"canonical_path": path, "alias_paths": []}]}), encoding="utf-8")
    near = tmp_path / "near.json"
    near.write_text(json.dumps({"groups": []}), encoding="utf-8")
    result = MODULE.audit(plan, exact, near)
    assert result["flag_counts"]["auto_exact_duplicate_violation"] == 1


def test_complete_content_identity_receipt_is_an_exact_guard(tmp_path):
    canonical = str((tmp_path / "a.wav").resolve())
    alias = str((tmp_path / "b.wav").resolve())
    plan = tmp_path / "plan.jsonl"
    _write_jsonl(plan, [{"record_type": "slo_rename_plan"},
                       {"path": alias, "decision": {"action": "suggest"}}])
    exact = tmp_path / "identity.json"
    exact.write_text(json.dumps({
        "record_type": "slo_content_identity_manifest",
        "duplicate_content_groups": {"hash": [canonical, alias]},
    }), encoding="utf-8")
    near = tmp_path / "near.json"
    near.write_text(json.dumps({"groups": []}), encoding="utf-8")
    result = MODULE.audit(plan, exact, near)
    assert result["source_exact_record_type"] == "slo_content_identity_manifest"
    assert result["flag_counts"]["exact_duplicate_alias"] == 1
