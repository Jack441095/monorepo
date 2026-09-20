#!/usr/bin/env python3
"""Cross-check SLO's derived receipts into one read-only readiness snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


VERSION = "end_state_readiness_snapshot_v1"


def _load(path: Path, record_type: str) -> dict[str, Any]:
    if record_type == "slo_rename_plan":
        with path.open(encoding="utf-8") as handle:
            payload = json.loads(next(handle))
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("record_type") != record_type:
        raise ValueError(f"{path} is not {record_type}")
    return payload


def build_snapshot(plan_path: Path, collections_path: Path, identity_path: Path,
                   content_index_path: Path, guard_path: Path,
                   approval_path: Path, labeller_path: Path | None = None,
                   class_gate_path: Path | None = None,
                   validation_labeller_path: Path | None = None,
                   class_gate_fusion_path: Path | None = None,
                   label_integrity_path: Path | None = None,
                   recalibration_path: Path | None = None) -> dict[str, Any]:
    plan = _load(plan_path, "slo_rename_plan")
    collections = _load(collections_path, "slo_review_collections")
    identity = _load(identity_path, "slo_content_identity_manifest")
    content_index = _load(content_index_path, "slo_content_addressed_embedding_index")
    guard = _load(guard_path, "slo_rename_duplicate_guard_audit")
    approval = _load(approval_path, "slo_rename_approval_gate_audit")
    labellers = _load(labeller_path, "slo_local_labeller_audit") if labeller_path else None
    class_gate = _load(class_gate_path, "slo_class_conditional_gate_testing_review") if class_gate_path else None
    validation_labeller = _load(validation_labeller_path, "slo_local_labeller_audit") if validation_labeller_path else None
    class_gate_fusion = _load(class_gate_fusion_path, "slo_class_gate_fusion_review_packet") if class_gate_fusion_path else None
    label_integrity = _load(label_integrity_path, "slo_completed_labelling_csv_integrity") if label_integrity_path else None
    recalibration = _load(recalibration_path, "slo_current_class_gate_recalibration") if recalibration_path else None
    errors = []
    n_plan = int(plan.get("n_files", -1))
    if n_plan != int(collections.get("n_plan_rows", -2)):
        errors.append("plan/collection row count mismatch")
    if n_plan != int(identity.get("n_input_paths", -3)):
        errors.append("plan/identity path count mismatch")
    if n_plan != int(content_index.get("n_embedding_rows", -4)):
        errors.append("plan/embedding row count mismatch")
    if n_plan != int(guard.get("n_plan_rows", -5)):
        errors.append("plan/duplicate guard row count mismatch")
    if int(approval.get("n_candidate_rows", 0)) != int(plan.get("actions", {}).get("suggest", 0)) + int(plan.get("actions", {}).get("auto_rename", 0)):
        errors.append("approval candidate count mismatch")
    approval_counts = approval.get("counts", {})
    auto_count = int(plan.get("actions", {}).get("auto_rename", 0))
    ready_count = int(approval_counts.get("ready_for_explicit_approval", 0))
    approval_blocked_count = int(approval_counts.get("blocked", 0))
    validation_labeller_complete = bool(
        validation_labeller and
        validation_labeller.get("summary", {}).get("total_done", 0) >=
        validation_labeller.get("summary", {}).get("total_queued", 1)
    )
    validation_integrity_complete = bool(
        label_integrity and
        label_integrity.get("summary", {}).get("all_complete", False)
    )
    validation_receipts_consistent = True
    if validation_labeller is not None and label_integrity is not None:
        validation_receipts_consistent = (
            validation_labeller_complete == validation_integrity_complete
        )
        if not validation_receipts_consistent:
            errors.append(
                "validation labeller audit disagrees with completed-label integrity receipt"
            )
    return {
        "record_type": "slo_end_state_readiness_snapshot",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "generated_from": {
            "plan": str(plan_path.resolve()),
            "collections": str(collections_path.resolve()),
            "identity": str(identity_path.resolve()),
            "content_index": str(content_index_path.resolve()),
            "duplicate_guard": str(guard_path.resolve()),
            "approval_gate": str(approval_path.resolve()),
        "labellers": str(labeller_path.resolve()) if labeller_path else None,
            "class_gate_queue": str(class_gate_path.resolve()) if class_gate_path else None,
            "validation_labeller": str(validation_labeller_path.resolve()) if validation_labeller_path else None,
            "class_gate_fusion": str(class_gate_fusion_path.resolve()) if class_gate_fusion_path else None,
            "label_integrity": str(label_integrity_path.resolve()) if label_integrity_path else None,
            "recalibration": str(recalibration_path.resolve()) if recalibration_path else None,
        },
        "corpus": {
            "n_files": n_plan,
            "n_content_ids": content_index.get("n_content_ids"),
            "n_alias_paths": content_index.get("n_alias_paths"),
            "embedding_dimensions": content_index.get("embedding_dimensions"),
        },
        "review_queues": collections.get("summary", {}),
        "duplicate_safety": {
            "flagged_paths": sum(bool(row.get("flags")) for row in guard.get("rows", [])),
            "flag_counts": guard.get("flag_counts", {}),
        },
        "approval": {
            "qualified_classes": approval.get("qualified_classes", []),
            "candidate_rows": approval.get("n_candidate_rows", 0),
            "counts": approval_counts,
            "auto_rows_in_plan": auto_count,
            "ready_for_explicit_approval": ready_count,
            "blocked_rows": approval_blocked_count,
        },
        "labellers": {
            "n_servers": (labellers or {}).get("summary", {}).get("n_servers"),
            "n_reachable": (labellers or {}).get("summary", {}).get("n_reachable"),
            "total_queued": (labellers or {}).get("summary", {}).get("total_queued"),
            "total_done": (labellers or {}).get("summary", {}).get("total_done"),
        },
        "class_gate_review": {
            "enabled": class_gate is not None,
            "n_candidates": (class_gate or {}).get("testing_summary", {}).get("n_review_candidates", 0),
            "candidate_classes": (class_gate or {}).get("candidate_classes", {}),
            "exact_duplicate_candidates": (class_gate or {}).get("testing_summary", {}).get("n_exact_duplicate_candidates", 0),
            "near_duplicate_candidates": (class_gate or {}).get("testing_summary", {}).get("n_near_duplicate_candidates", 0),
            "auto_approved": False,
        },
        "validation_labeller": {
            "n_servers": (validation_labeller or {}).get("summary", {}).get("n_servers"),
            "n_reachable": (validation_labeller or {}).get("summary", {}).get("n_reachable"),
            "total_queued": (validation_labeller or {}).get("summary", {}).get("total_queued"),
            "total_done": (validation_labeller or {}).get("summary", {}).get("total_done"),
            "complete": validation_labeller_complete,
            "integrity_complete": validation_integrity_complete,
            "receipts_consistent": validation_receipts_consistent,
        },
        "class_gate_fusion_review": {
            "enabled": class_gate_fusion is not None,
            "n_candidates": (class_gate_fusion or {}).get("summary", {}).get("n_rows", 0),
            "fusion_states": (class_gate_fusion or {}).get("summary", {}).get("fusion_states", {}),
            "decision": (class_gate_fusion or {}).get("decision", "review-only"),
            "auto_approved": bool((class_gate_fusion or {}).get("safety", {}).get("auto_approved", False)),
        },
        "label_integrity": {
            "enabled": label_integrity is not None,
            "n_files": (label_integrity or {}).get("summary", {}).get("n_files", 0),
            "n_rows": (label_integrity or {}).get("summary", {}).get("n_rows", 0),
            "all_integrity_ok": (label_integrity or {}).get("summary", {}).get("all_integrity_ok", False),
            "all_complete": (label_integrity or {}).get("summary", {}).get("all_complete", False),
            "labels_promoted_to_gold": False,
        },
        "class_gate_recalibration": {
            "enabled": recalibration is not None,
            "inventory": (recalibration or {}).get("inventory", {}),
            "results": (recalibration or {}).get("results", []),
            "decision": (recalibration or {}).get("decision", "review-only"),
            "production_model_changed": False,
        },
        "readiness": {
            "mode": "review_only" if auto_count == 0 else "approval_required",
            # A partial approval is useful for review, but it is not a complete
            # apply-ready state: the rename executor selects the whole plan and
            # must refuse any remaining blocked rows.
            "ready_to_apply": bool(ready_count and approval_blocked_count == 0 and not errors),
            "labels_required_for_new_qualification": True,
            "labelling_handoff_ready": bool(labellers and labellers.get("summary", {}).get("n_reachable") == labellers.get("summary", {}).get("n_servers")),
            "class_gate_review_available": bool(class_gate is not None),
            "validation_labels_complete": bool(
                validation_labeller_complete and
                validation_integrity_complete and
                validation_receipts_consistent
            ),
            "completed_label_integrity_ok": bool(
                label_integrity and label_integrity.get("summary", {}).get("all_integrity_ok", False)
            ),
            "class_gate_recalibration_available": recalibration is not None,
            "source_audio_modified": False,
            "rename_actions_applied": False,
            "gpu_1_touched": False,
        },
        "errors": errors,
        "input_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in {
            "plan": plan_path, "collections": collections_path, "identity": identity_path,
            "content_index": content_index_path, "duplicate_guard": guard_path,
            "approval_gate": approval_path,
        }.items()},
        "safety": {
            "read_only": True,
            "source_audio_modified": False,
            "plans_modified": False,
            "approval_granted": False,
            "rename_actions": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "collections", "identity", "content-index", "duplicate-guard", "approval-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--labeller-audit", type=Path)
    parser.add_argument("--class-gate-queue", type=Path)
    parser.add_argument("--validation-labeller-audit", type=Path)
    parser.add_argument("--class-gate-fusion", type=Path)
    parser.add_argument("--label-integrity", type=Path)
    parser.add_argument("--recalibration", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = build_snapshot(args.plan, args.collections, args.identity, args.content_index,
                            args.duplicate_guard, args.approval_gate, args.labeller_audit,
                            args.class_gate_queue, args.validation_labeller_audit,
                            args.class_gate_fusion, args.label_integrity, args.recalibration)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"corpus": result["corpus"], "review_queues": result["review_queues"], "readiness": result["readiness"], "errors": result["errors"]}, indent=2))


if __name__ == "__main__":
    main()
