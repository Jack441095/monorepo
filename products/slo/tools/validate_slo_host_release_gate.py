#!/usr/bin/env python3
"""Validate the fail-closed SLO host/release gate preparation."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def validate(root: Path, manifest_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"cannot parse manifest: {exc}"]
    if manifest.get("schema_version") != "slo_host_release_gate_candidate_v1":
        errors.append("unexpected schema_version")
    if manifest.get("status") != "environment_gate_pending":
        errors.append("gate must remain environment-pending")
    if manifest.get("product") != "slo":
        errors.append("product must be slo")
    if not manifest.get("package_id"):
        errors.append("package_id must be present")
    candidate = manifest.get("candidate", {})
    for key in ("worktree", "branch", "source_checkpoint", "qualification_descendant", "build_entry_descendant"):
        if not isinstance(candidate.get(key), str) or not candidate.get(key):
            errors.append(f"candidate.{key} must be present")
    if not isinstance(candidate.get("dirty_entries"), int) or candidate.get("dirty_entries") < 0:
        errors.append("candidate.dirty_entries must be a non-negative integer")
    try:
        branch_result = subprocess.run(
            ["git", "-C", str(root), "branch", "--show-current"],
            check=False,
            capture_output=True,
            text=True,
        )
        ancestry_result = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", candidate.get("source_checkpoint", ""), "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
        status_result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        errors.append(f"candidate Git metadata check failed: {exc}")
    else:
        if branch_result.returncode != 0 or branch_result.stdout.strip() != candidate.get("branch"):
            errors.append("candidate branch does not match the live worktree")
        if ancestry_result.returncode != 0:
            errors.append("candidate source checkpoint is not an ancestor of the live worktree")
        live_dirty = len(status_result.stdout.splitlines()) if status_result.returncode == 0 else -1
        if live_dirty != candidate.get("dirty_entries"):
            errors.append("candidate dirty-entry count does not match the live worktree")
    if candidate.get("release_authorized") is not False:
        errors.append("candidate.release_authorized must be false")
    planned_gates = manifest.get("planned_gates", {})
    required_gates = {
        "au_validation",
        "vst3_validation",
        "ableton_live_scan_load_render_state_reopen",
        "clean_machine_install_launch_uninstall",
        "signing_notarisation",
        "licensing_staging",
        "support_rollback_rehearsal",
        "large_library_capacity",
    }
    missing_gates = sorted(required_gates.difference(planned_gates))
    if missing_gates:
        errors.append(f"planned_gates missing: {', '.join(missing_gates)}")
    requirements = manifest.get("environment_requirements", {})
    for key in ("owner_approval", "host_session_available", "developer_id_credentials_available", "staging_license_authority_available", "external_private_data_required"):
        if requirements.get(key) is not False:
            errors.append(f"environment_requirements.{key} must be false")
    controls = manifest.get("scope_controls", {})
    for key in ("shared_slo_checkout_modified", "protected_data_opened_or_moved", "credentials_opened_or_used", "production_service_contacted", "external_action_taken"):
        if controls.get(key) is not False:
            errors.append(f"scope_controls.{key} must be false")
    quality = manifest.get("quality", {})
    for key in ("host_qualified", "release_qualified", "public_claims_authorized"):
        if quality.get(key) is not False:
            errors.append(f"quality.{key} must be false")
    if not isinstance(manifest.get("next_package"), str) or not manifest["next_package"].strip():
        errors.append("next_package must be present")
    for item in (
        "SmartSampleManager/CMakePresets.json",
        "validation/audits/stage-2-slo-host-release-gate-v1/SLO_HOST_RELEASE_GATE_MANIFEST_V1.json",
    ):
        if not (root / item).is_file():
            errors.append(f"required file missing: {item}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--manifest", type=Path, default=Path(__file__).parents[1] / "validation/audits/stage-2-slo-host-release-gate-v1/SLO_HOST_RELEASE_GATE_MANIFEST_V1.json")
    args = parser.parse_args()
    errors = validate(args.root, args.manifest)
    if errors:
        print("INVALID SLO host/release gate")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("VALID SLO host/release gate: environment pending; release remains blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
