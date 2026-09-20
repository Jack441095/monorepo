import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_end_state_readiness_snapshot.py")
SPEC = importlib.util.spec_from_file_location("build_end_state_readiness_snapshot", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _write(path, record_type, **extra):
    value = {"record_type": record_type, **extra}
    path.write_text(json.dumps(value), encoding="utf-8")


def test_snapshot_cross_checks_counts_and_stays_review_only(tmp_path):
    files = {}
    for name, record_type, extra in [
        ("plan", "slo_rename_plan", {"n_files": 2, "actions": {"suggest": 1, "auto_rename": 0}}),
        ("collections", "slo_review_collections", {"n_plan_rows": 2, "summary": {"suggest": 1}}),
        ("identity", "slo_content_identity_manifest", {"n_input_paths": 2}),
        ("content", "slo_content_addressed_embedding_index", {"n_embedding_rows": 2, "n_content_ids": 2, "n_alias_paths": 0, "embedding_dimensions": 4}),
        ("guard", "slo_rename_duplicate_guard_audit", {"n_plan_rows": 2, "rows": [{"flags": []}, {"flags": []}], "flag_counts": {}}),
        ("approval", "slo_rename_approval_gate_audit", {"n_candidate_rows": 1, "qualified_classes": [], "counts": {"blocked": 1}}),
    ]:
        files[name] = tmp_path / f"{name}.json"
        _write(files[name], record_type, **extra)
    result = MODULE.build_snapshot(files["plan"], files["collections"], files["identity"], files["content"], files["guard"], files["approval"])
    assert result["errors"] == []
    assert result["readiness"]["mode"] == "review_only"
    assert result["readiness"]["ready_to_apply"] is False


def test_snapshot_keeps_partial_approval_review_only(tmp_path):
    files = {}
    for name, record_type, extra in [
        ("plan", "slo_rename_plan", {"n_files": 2, "actions": {"suggest": 2, "auto_rename": 0}}),
        ("collections", "slo_review_collections", {"n_plan_rows": 2, "summary": {"suggest": 2}}),
        ("identity", "slo_content_identity_manifest", {"n_input_paths": 2}),
        ("content", "slo_content_addressed_embedding_index", {"n_embedding_rows": 2, "n_content_ids": 2, "n_alias_paths": 0, "embedding_dimensions": 4}),
        ("guard", "slo_rename_duplicate_guard_audit", {"n_plan_rows": 2, "rows": [{"flags": []}, {"flags": []}], "flag_counts": {}}),
        ("approval", "slo_rename_approval_gate_audit", {"n_candidate_rows": 2, "qualified_classes": [], "counts": {"ready_for_explicit_approval": 1, "blocked": 1}}),
    ]:
        files[name] = tmp_path / f"{name}.json"
        _write(files[name], record_type, **extra)
    result = MODULE.build_snapshot(files["plan"], files["collections"], files["identity"], files["content"], files["guard"], files["approval"])
    assert result["approval"]["blocked_rows"] == 1
    assert result["readiness"]["ready_to_apply"] is False


def test_snapshot_records_class_gate_and_validation_state(tmp_path):
    files = {}
    for name, record_type, extra in [
        ("plan", "slo_rename_plan", {"n_files": 1, "actions": {"suggest": 0, "auto_rename": 0}}),
        ("collections", "slo_review_collections", {"n_plan_rows": 1, "summary": {}}),
        ("identity", "slo_content_identity_manifest", {"n_input_paths": 1}),
        ("content", "slo_content_addressed_embedding_index", {"n_embedding_rows": 1, "n_content_ids": 1, "n_alias_paths": 0, "embedding_dimensions": 4}),
        ("guard", "slo_rename_duplicate_guard_audit", {"n_plan_rows": 1, "rows": [{"flags": []}], "flag_counts": {}}),
        ("approval", "slo_rename_approval_gate_audit", {"n_candidate_rows": 0, "qualified_classes": [], "counts": {}}),
        ("class_gate", "slo_class_conditional_gate_testing_review", {"testing_summary": {"n_review_candidates": 2, "n_exact_duplicate_candidates": 1, "n_near_duplicate_candidates": 1}, "candidate_classes": {"Kick": 0.8}}),
        ("class_gate_fusion", "slo_class_gate_fusion_review_packet", {"summary": {"n_rows": 2, "fusion_states": {"audio_name_agree": 1, "audio_name_conflict": 1}}, "decision": "review-only", "safety": {"auto_approved": False}}),
        ("label_integrity", "slo_completed_labelling_csv_integrity", {"summary": {"n_files": 2, "n_rows": 3, "all_integrity_ok": True, "all_complete": False}, "safety": {"labels_promoted_to_gold": False}}),
        ("validation", "slo_local_labeller_audit", {"summary": {"n_servers": 1, "n_reachable": 1, "total_queued": 2, "total_done": 0}}),
        ("recalibration", "slo_current_class_gate_recalibration", {"inventory": {"n_rows": 2}, "results": [], "decision": "research audit only"}),
    ]:
        files[name] = tmp_path / f"{name}.json"
        _write(files[name], record_type, **extra)
    result = MODULE.build_snapshot(
        files["plan"], files["collections"], files["identity"], files["content"],
        files["guard"], files["approval"], class_gate_path=files["class_gate"],
        validation_labeller_path=files["validation"], class_gate_fusion_path=files["class_gate_fusion"],
        label_integrity_path=files["label_integrity"], recalibration_path=files["recalibration"])
    assert result["class_gate_review"]["n_candidates"] == 2
    assert result["class_gate_review"]["auto_approved"] is False
    assert result["readiness"]["validation_labels_complete"] is False
    assert result["class_gate_fusion_review"]["n_candidates"] == 2
    assert result["class_gate_fusion_review"]["auto_approved"] is False
    assert result["label_integrity"]["all_integrity_ok"] is True
    assert result["label_integrity"]["all_complete"] is False
    assert result["readiness"]["completed_label_integrity_ok"] is True
    assert result["class_gate_recalibration"]["enabled"] is True
    assert result["readiness"]["class_gate_recalibration_available"] is True


def test_snapshot_rejects_disagreeing_validation_receipts(tmp_path):
    files = {}
    for name, record_type, extra in [
        ("plan", "slo_rename_plan", {"n_files": 1, "actions": {"suggest": 0, "auto_rename": 0}}),
        ("collections", "slo_review_collections", {"n_plan_rows": 1, "summary": {}}),
        ("identity", "slo_content_identity_manifest", {"n_input_paths": 1}),
        ("content", "slo_content_addressed_embedding_index", {"n_embedding_rows": 1, "n_content_ids": 1, "n_alias_paths": 0, "embedding_dimensions": 4}),
        ("guard", "slo_rename_duplicate_guard_audit", {"n_plan_rows": 1, "rows": [{"flags": []}], "flag_counts": {}}),
        ("approval", "slo_rename_approval_gate_audit", {"n_candidate_rows": 0, "qualified_classes": [], "counts": {}}),
        ("validation", "slo_local_labeller_audit", {"summary": {"n_servers": 1, "n_reachable": 1, "total_queued": 2, "total_done": 0}}),
        ("label_integrity", "slo_completed_labelling_csv_integrity", {"summary": {"n_files": 1, "n_rows": 2, "all_integrity_ok": True, "all_complete": True}}),
    ]:
        files[name] = tmp_path / f"{name}.json"
        _write(files[name], record_type, **extra)
    result = MODULE.build_snapshot(
        files["plan"], files["collections"], files["identity"], files["content"],
        files["guard"], files["approval"],
        validation_labeller_path=files["validation"],
        label_integrity_path=files["label_integrity"],
    )
    assert result["validation_labeller"]["receipts_consistent"] is False
    assert result["readiness"]["validation_labels_complete"] is False
    assert result["errors"] == [
        "validation labeller audit disagrees with completed-label integrity receipt"
    ]
